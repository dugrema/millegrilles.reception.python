import asyncio
import datetime
import json
import logging

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

        self.date_post = int(datetime.datetime.utcnow().timestamp())

    async def generer(self, etat: EtatReception):
        message_dechiffre = {
            'contenu': self.contenu,
            'date_post': self.date_post
        }

        if self.destinataires:
            message_dechiffre['destinataires'] = self.destinataires
        else:
            raise Exception('Il faut fournir user_id ou nom_usager')

        if self.reply_to:
            message_dechiffre['reply_to'] = self.reply_to

        certificats_chiffrage = etat.get_certificats_chiffrage()
        message_chiffre = await etat.formatteur_message.chiffrer_message(
            certificats_chiffrage, 8, message_dechiffre, Constantes.DOMAINE_MESSAGES, 'posterV1')

        return message_chiffre


class MessageReceptionHandler:

    def __init__(self, etat: EtatReception):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat = etat

        self.__semaphore_messages = asyncio.BoundedSemaphore(value=3)

    async def recevoir_post_web(self, request: Request):
        async with self.__semaphore_messages:
            message_post = await request.json()

            try:
                message_prepare = MessagePrepare.parse(message_post)
                return await self.submit_message(message_prepare)
            except asyncio.TimeoutError:
                self.__logger.error("Timeout error sur posterV1")
                return web.HTTPInternalServerError()
            except Exception:
                self.__logger.exception("Exception sur posterV1")
                return web.HTTPInternalServerError()

    async def submit_message(self, message_prepare: MessagePrepare):
        producer = await asyncio.wait_for(self.__etat.producer_wait(), 5)

        if producer is None:
            raise Exception('producer non pret')

        try:
            message_chiffre, message_id = await message_prepare.generer(self.__etat)
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
            # HTTP 201 : Indiquer que le message a ete cree
            return web.HTTPCreated(body=json.dumps(reponse_parsed))
        else:
            # HTTP 200 : Indique un resultat en erreur
            return web.HTTPOk(body=json.dumps(reponse_parsed))


