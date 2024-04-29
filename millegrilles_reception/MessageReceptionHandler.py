import asyncio
import json
import logging

from aiohttp import web
from aiohttp.web_request import Request
from typing import Optional

from millegrilles_messages.messages import Constantes
from millegrilles_reception.EtatReception import EtatReception


class MessagePrepare:

    def __init__(self):
        self.user_id: Optional[list[str]] = None
        self.nom_usager: Optional[list[str]] = None
        self.contenu: Optional[str] = None
        self.reply_to: Optional[str] = None

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

        nom_usager = message_recu.get('nom_usager')
        if nom_usager is not None:
            if isinstance(nom_usager, str):
                self.nom_usager = [nom_usager]
            elif isinstance(nom_usager, list):
                self.nom_usager = nom_usager
            else:
                raise Exception('nom_usager invalide')

        self.reply_to = message_recu.get('reply_to')

    async def generer(self, etat: EtatReception):
        message_dechiffre = {
            'contenu': self.contenu
        }

        if self.user_id:
            message_dechiffre['user_id'] = self.user_id
        elif self.nom_usager:
            message_dechiffre['nom_usager'] = self.nom_usager
        else:
            raise Exception('Il faut fournir user_id ou nom_usager')

        if self.reply_to:
            message_dechiffre['reply_to'] = self.reply_to

        certificats_chiffrage = etat.get_certificats_chiffrage()
        message_chiffre = await etat.formatteur_message.chiffrer_message(
            certificats_chiffrage, 8, self.contenu, Constantes.DOMAINE_MESSAGES, 'posterV1')

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
                await self.submit_message(message_prepare)
                return web.HTTPOk()
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

        message_chiffre, message_id = await message_prepare.generer(self.__etat)

        message_bytes = json.dumps(message_chiffre)

        rk = ['commande', Constantes.DOMAINE_MESSAGES, 'posterV1']
        reponse = await producer.emettre_attendre(
            message_bytes, '.'.join(rk),
            exchange=Constantes.SECURITE_PUBLIC,
            correlation_id=message_id,
            timeout=10
        )

        if reponse.parsed.get('ok') is not True:
            raise Exception('submit_message Erreur traitement %s' % reponse.parsed.get('err'))
