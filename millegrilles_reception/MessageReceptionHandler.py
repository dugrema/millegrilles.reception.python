import asyncio
import datetime
import json
import logging
import uuid
import shutil

from aiohttp import web
from aiohttp.web_request import Request
from typing import Optional

from millegrilles_messages.messages import Constantes
from millegrilles_reception.EtatReception import EtatReception


class MessagePrepare:

    def __init__(self):
        self.destinataires: Optional[list[str]] = None
        self.contenu: Optional[str] = None
        self.reply_to: Optional[str] = None
        self.date_post: Optional[int] = None
        self.auteur: Optional[str] = None

    @staticmethod
    def parse(message_recu: dict):
        message = MessagePrepare()

        if message_recu.get('sig'):
            # On a un message signe, verifier
            message.parse_chiffre(message_recu)
        else:
            message.parse_dechiffre(message_recu)

        return message

    def parse_chiffre(self, message_recu: dict):
        raise NotImplementedError("todo")

    def parse_dechiffre(self, message_recu: dict):
        self.contenu = message_recu['contenu']

        user_id = message_recu.get('user_id')
        if user_id is not None:
            if isinstance(user_id, str):
                self.user_id = [user_id]
            elif isinstance(user_id, list):
                self.user_id = user_id
            else:
                raise Exception('user_id invalide')

        destinataire = message_recu['destinataires']
        if isinstance(destinataire, str):
            self.destinataires = [destinataire]
        elif isinstance(destinataire, list):
            self.destinataires = destinataire
        else:
            raise Exception('destinataire invalide')

        self.reply_to = message_recu.get('reply_to')
        self.auteur = message_recu.get('auteur')

        self.date_post = int(datetime.datetime.utcnow().timestamp())

    async def generer(self, etat: EtatReception, additionnel: Optional[dict] = None):
        message_dechiffre = {
            'contenu': self.contenu,
            'date_post': self.date_post
        }

        if additionnel:
            message_dechiffre.update(additionnel)

        if self.destinataires:
            message_dechiffre['destinataires'] = self.destinataires
        else:
            raise Exception('Il faut fournir user_id ou nom_usager')

        if self.reply_to:
            message_dechiffre['reply_to'] = self.reply_to

        if self.auteur:
            message_dechiffre['auteur'] = self.auteur

        certificats_chiffrage = etat.get_certificats_chiffrage()
        message_chiffre = await etat.formatteur_message.chiffrer_message(
            certificats_chiffrage, 8, message_dechiffre, Constantes.DOMAINE_MESSAGES, 'posterV1')

        return message_chiffre


class MessageReceptionHandler:

    def __init__(self, web_app):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__web_app = web_app
        self.__etat = web_app.etat

        self.__semaphore_messages = asyncio.BoundedSemaphore(value=3)

    async def recevoir_post_web(self, request: Request):
        batch_id = str(uuid.uuid4())
        fichiers_traites = None

        async with self.__semaphore_messages:
            headers_web = dict(request.headers)
            self.__logger.debug("Reception recevoir_post_web headers:\n%s" % json.dumps(headers_web, indent=2))

            if request.content_type.startswith('multipart'):
                # On recoit un message avec des fichiers attaches
                reader = await request.multipart()

                message_post = dict()
                fichiers_traites = list()

                async for field in reader:
                    if field.name == 'files[]':
                        fichier_traiter = await self.__web_app.fichiers_dechiffres_handler.recevoir_fichier(batch_id, field)
                        fichiers_traites.append(fichier_traiter)
                    elif field.name == 'message':
                        message_post = await field.read(decode=True)
                        message_post = json.loads(message_post.decode('utf-8'))
                    else:
                        return web.HTTPBadRequest(reason="champ non supporte, utiliser files[] et message")
            elif request.content_type == 'application/json':
                message_post = await request.json()
                # Desactiver traitement fichiers (aucuns recus)
                batch_id = None
                fichiers_traites = None
            else:
                return web.HTTPBadRequest(reason="mimetype non supporte")

            try:
                origine = json.dumps(headers_web)
                message_prepare = MessagePrepare.parse(message_post)
                return await self.submit_message(message_prepare, {'origine': origine}, batch_id, fichiers_traites)
            except asyncio.TimeoutError:
                self.__logger.error("Timeout error sur posterV1")
                return web.HTTPInternalServerError()
            except Exception:
                self.__logger.exception("Exception sur posterV1")
                return web.HTTPInternalServerError()

        # shutil.rmtree()

    async def submit_message(self, message_prepare: MessagePrepare, headers_web: dict,
                             fichiers_batch_id: Optional[str] = None, fichiers_traites: Optional[list] = None):
        producer = await asyncio.wait_for(self.__etat.producer_wait(), 5)

        if producer is None:
            raise Exception('producer non pret')

        try:
            additionnel = headers_web.copy()
            if fichiers_traites is not None and len(fichiers_traites) > 0:
                additionnel['fichiers'] = fichiers_traites
            message_chiffre, message_id = await message_prepare.generer(self.__etat, additionnel)
        except KeyError:
            return web.HTTPOk(body=json.dumps({'ok': False, 'code': 2, 'err': 'Cles de chiffrage non recues, reessayer dans 30 secondes'}))

        message_bytes = json.dumps(message_chiffre)

        rk = ['commande', Constantes.DOMAINE_MESSAGES, 'posterV1']
        reponse = await producer.emettre_attendre(
            message_bytes, '.'.join(rk),
            exchange=Constantes.SECURITE_PUBLIC,
            correlation_id=message_id,
            timeout=10
        )

        reponse_parsed = reponse.parsed
        del reponse_parsed['__original']

        if reponse_parsed.get('ok') is True:
            if fichiers_batch_id is not None:
                self.__logger.info("submit_message Submit consignation fichiers batch_id %s" % fichiers_batch_id)
                await self.__web_app.fichiers_dechiffres_handler.intake_batch(fichiers_batch_id)

            # HTTP 201 : Indiquer que le message a ete cree
            return web.HTTPCreated(body=json.dumps(reponse_parsed))
        else:
            # HTTP 200 : Indique un resultat en erreur
            return web.HTTPOk(body=json.dumps(reponse_parsed))
