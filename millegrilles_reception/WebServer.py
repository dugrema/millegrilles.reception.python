import asyncio
import logging
import pathlib

from aiohttp import web
from aiohttp.web_request import Request
from typing import Optional

from millegrilles_web.WebServer import WebServer
from millegrilles_web.TransfertFichiers import ReceptionFichiersMiddleware

from millegrilles_reception import Constantes as ConstantesReception
from millegrilles_reception.MessageReceptionHandler import MessageReceptionHandler
from millegrilles_reception.FichiersDechiffresHandler import FichiersDechiffresHandler


class WebServerReception(WebServer):

    def __init__(self, etat, commandes, messages_handler: MessageReceptionHandler,
                 fichiers_dechiffres_handler: FichiersDechiffresHandler):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        super().__init__(ConstantesReception.WEB_APP_PATH, etat, commandes)
        self.__messages_handler = messages_handler
        self.__fichiers_dechiffres_handler = fichiers_dechiffres_handler

        self.__semaphore_web = asyncio.BoundedSemaphore(value=5)

        self.__reception_fichiers = ReceptionFichiersMiddleware(
            self.app, self.etat, '/reception/fichiers/upload')

    def get_nom_app(self) -> str:
        return ConstantesReception.APP_NAME

    async def setup(self, configuration: Optional[dict] = None, stop_event: Optional[asyncio.Event] = None):
        # await super().setup(configuration, stop_event)
        if stop_event is not None:
            self._stop_event = stop_event
        else:
            self._stop_event = asyncio.Event()

        self._charger_configuration(configuration)
        self._charger_ssl()
        await self._preparer_routes()
        await self.__reception_fichiers.setup()

    async def setup_socketio(self):
        pass  # Socket-io n'est pas utilise

    async def _preparer_routes(self):
        self.__logger.info("Preparer routes WebServerCollections sous /collections")
        # await super()._preparer_routes()
        self._app.add_routes([
            web.get(f'{self.app_path}/info.json', self.handle_info_session),
            web.post(f'{self.app_path}/message', self.__messages_handler.recevoir_post_web),
        ])

    async def run(self):
        """
        Override pour ajouter thread reception fichiers
        :return:
        """
        self.__logger.info("Running")

        tasks = [
            super().run(),
            self.__reception_fichiers.run(self._stop_event)
        ]

        await asyncio.tasks.wait(tasks, return_when=asyncio.tasks.FIRST_COMPLETED)

        self.__logger.info("Run termine")

    async def handle_info_session(self, request: Request):
        async with self.__semaphore_web:
            return web.HTTPOk()

    @property
    def fichiers_dechiffres_handler(self):
        return self.__fichiers_dechiffres_handler

    async def ajouter_upload(self, path_upload: pathlib.Path):
        await self.__reception_fichiers.ajouter_upload(path_upload)
