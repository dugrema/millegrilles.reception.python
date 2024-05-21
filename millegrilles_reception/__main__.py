import argparse
import asyncio
import datetime
import logging
import signal

from typing import Optional

from millegrilles_messages.docker.Entretien import TacheEntretien

from millegrilles_web.WebAppMain import WebAppMain

from millegrilles_web.WebAppMain import LOGGING_NAMES as LOGGING_NAMES_WEB, adjust_logging
from millegrilles_reception.WebServer import WebServerReception
from millegrilles_reception.Commandes import CommandReceptionHandler
from millegrilles_reception.EtatReception import EtatReception
from millegrilles_reception.MessageReceptionHandler import MessageReceptionHandler
from millegrilles_reception.FichiersDechiffresHandler import FichiersDechiffresHandler

logger = logging.getLogger(__name__)

LOGGING_NAMES = ['millegrilles_reception']
LOGGING_NAMES.extend(LOGGING_NAMES_WEB)


class ReceptionAppMain(WebAppMain):

    def __init__(self):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        super().__init__()
        self.__reception_handler: Optional[MessageReceptionHandler] = None
        self.__fichier_dechiffres_handler: Optional[FichiersDechiffresHandler] = None
        # self.__fichier_intake: Optional[FichierIntake] = None

    def init_etat(self):
        return EtatReception(self.config)

    def init_command_handler(self) -> CommandReceptionHandler:
        reception_handler = CommandReceptionHandler(self)

        self.__fichier_dechiffres_handler = FichiersDechiffresHandler(self)

        return reception_handler

    async def configurer(self):
        await super().configurer()
        await self.__fichier_dechiffres_handler.setup()

        self.etat.ajouter_tache_entretien(
            TacheEntretien(datetime.timedelta(minutes=10), self.etat.charger_cles_chiffrage))
        self.etat.ajouter_tache_entretien(
            TacheEntretien(datetime.timedelta(minutes=20), self.etat.nettoyer_certificats_stale))

    async def configurer_web_server(self):
        self.__reception_handler = MessageReceptionHandler(self.etat)
        self._web_server = WebServerReception(self.etat, self._commandes_handler, self.__reception_handler,
                                              self.__fichier_dechiffres_handler)
        await self._web_server.setup(stop_event=self._stop_event)

    def exit_gracefully(self, signum=None, frame=None):
        self.__logger.info("Fermer application, signal: %d" % signum)
        self._stop_event.set()

    def parse(self) -> argparse.Namespace:
        args = super().parse()
        adjust_logging(LOGGING_NAMES, args)
        return args

    @property
    def nb_reply_correlation_max(self):
        return 50

    @property
    def reception_handler(self):
        return self.__reception_handler


async def demarrer():
    main_inst = ReceptionAppMain()

    signal.signal(signal.SIGINT, main_inst.exit_gracefully)
    signal.signal(signal.SIGTERM, main_inst.exit_gracefully)

    await main_inst.configurer()
    logger.info("Run main collections")
    await main_inst.run()
    logger.info("Fin main collections")


def main():
    """
    Methode d'execution de l'application
    :return:
    """
    logging.basicConfig()
    for log in LOGGING_NAMES:
        logging.getLogger(log).setLevel(logging.INFO)
    asyncio.run(demarrer())


if __name__ == '__main__':
    main()
