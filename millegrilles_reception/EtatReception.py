import asyncio
import datetime

from dataclasses import dataclass

from millegrilles_messages.messages.EnveloppeCertificat import EnveloppeCertificat

from millegrilles_web.Configuration import ConfigurationApplicationWeb
from millegrilles_web.EtatWeb import EtatWeb


@dataclass
class CertificatChiffrage:
    enveloppe: EnveloppeCertificat
    fingerprint: str
    date_ajout: datetime.datetime

    @staticmethod
    def from_enveloppe(enveloppe: EnveloppeCertificat):
        return CertificatChiffrage(enveloppe, enveloppe.fingerprint, datetime.datetime.utcnow())


class EtatReception(EtatWeb):

    def __init__(self, configuration: ConfigurationApplicationWeb):
        super().__init__(configuration)

        # Certificats par fingerprint
        self.__certificat_chiffrage: dict[str, EnveloppeCertificat] = dict()

    # async def run(self, stop_event: asyncio.Event, rabbitmq_dao):
    #     async with asyncio.TaskGroup() as tg:
    #         tg.create_task(super().run(stop_event, rabbitmq_dao))
    #         tg.create_task(self.charger_consignation_thread(stop_event))
    #
    #     return await super().run(stop_event, rabbitmq_dao)

    async def charger_cles_chiffrage_thread(self, stop_event: asyncio.Event):
        while stop_event.is_set() is False:
            await self.charger_cles_chiffrage()
            await asyncio.sleep(300)

    async def charger_cles_chiffrage(self):
        """
        Charge les cles de chiffrage (maitre des cles et domaine messages)
        :return:
        """
        producer = self.producer
        if producer is None:
            raise Exception('producer pas pret')
        await asyncio.wait_for(producer.producer_pret().wait(), 5)

        raise NotImplementedError('todo')

    def nettoyer_certificats_stale(self):
        fingerprints_stale = list()

        # Detecter certificats ajoutes/maj il y a plus de 20 minutes
        expiration = datetime.datetime.utcnow() - datetime.timedelta(minutes=20)
        for fingerprint, cert in self.__certificat_chiffrage:
            if cert.date_ajout < expiration:
                fingerprints_stale.append(fingerprint)

        # Retirer certificats stale
        for fingerprint in fingerprints_stale:
            del self.__certificat_chiffrage[fingerprint]

    async def recevoir_certificat_chiffrage(self, certificat: list):
        """
        Recoit un certificat de chiffrate (maitre des cles, domaine messages) recu via un evenement.

        :param certificat: Chaine de PEMs
        """
        enveloppe = EnveloppeCertificat.from_pem(certificat)
        self.__certificat_chiffrage[enveloppe.fingerprint] = CertificatChiffrage.from_enveloppe(enveloppe)

    def chiffrer_cle_secrete(self, cle_secrete: bytes):
        cles_chiffrees = dict()

        for fingerprint, cert in self.__certificat_chiffrage:
            cle_chiffree, _fingerprint = cert.chiffrage_asymmetrique(cle_secrete)
            cles_chiffrees[fingerprint] = cle_chiffree

        if len(cles_chiffrees) == 0:
            raise Exception("Aucuns certificats de chiffrage disponible")

        return cles_chiffrees
