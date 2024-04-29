import asyncio
import datetime
import logging

from dataclasses import dataclass

from millegrilles_messages.messages.EnveloppeCertificat import EnveloppeCertificat
from millegrilles_messages.messages.MessagesModule import MessageWrapper

from millegrilles_web.Configuration import ConfigurationApplicationWeb
from millegrilles_web.EtatWeb import EtatWeb

from millegrilles_messages.messages import Constantes


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

        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        # Certificats par fingerprint
        self.__certificat_chiffrage: dict[str, CertificatChiffrage] = dict()

    async def charger_cles_chiffrage(self):
        """
        Charge les cles de chiffrage (maitre des cles et domaine messages)
        :return:
        """
        producer = self.producer
        if producer is None:
            raise Exception('producer pas pret')
        await asyncio.wait_for(producer.producer_pret().wait(), 5)

        certificat_trouve = False

        # Charger certificats de maitre des cles
        try:
            reponse = await producer.executer_requete(
                dict(), Constantes.DOMAINE_MAITRE_DES_CLES, Constantes.REQUETE_MAITREDESCLES_CERTIFICAT, Constantes.SECURITE_PUBLIC)
            certificat = reponse.certificat
            if Constantes.DOMAINE_MAITRE_DES_CLES in certificat.get_domaines:
                self.__certificat_chiffrage[certificat.fingerprint] = CertificatChiffrage.from_enveloppe(certificat)
                certificat_trouve = True
        except Exception as e:
            self.__logger.warning("EtatReception.charger_cles_chiffrage Erreur chargement certificats maitre des cles : %s" % str(e))

        # Charger certificat de domaine messages
        try:
            reponse = await producer.executer_requete(
                dict(), Constantes.DOMAINE_MESSAGES, Constantes.REQUETE_MESSAGES_CERTIFICAT, Constantes.SECURITE_PUBLIC)
            certificat = reponse.certificat
            if Constantes.DOMAINE_MESSAGES in certificat.get_domaines:
                self.__certificat_chiffrage[certificat.fingerprint] = CertificatChiffrage.from_enveloppe(certificat)
                certificat_trouve = True
        except Exception as e:
            self.__logger.warning(
                "EtatReception.charger_cles_chiffrage Erreur chargement certificats domaine messages : %s" % str(e))

        if certificat_trouve is False:
            raise Exception('Aucun certificat de chiffrage trouve')

    async def nettoyer_certificats_stale(self):
        fingerprints_stale = list()

        # Detecter certificats ajoutes/maj il y a plus de 20 minutes
        expiration = datetime.datetime.utcnow() - datetime.timedelta(minutes=20)
        for fingerprint, cert in self.__certificat_chiffrage.items():
            if cert.date_ajout < expiration:
                fingerprints_stale.append(fingerprint)

        # Retirer certificats stale
        for fingerprint in fingerprints_stale:
            del self.__certificat_chiffrage[fingerprint]

    def recevoir_certificat_chiffrage(self, message: MessageWrapper):
        """
        Recoit un certificat de chiffrate (maitre des cles, domaine messages) recu via un evenement.

        :param certificat: Chaine de PEMs
        """
        enveloppe = message.certificat
        domaines_certificat = enveloppe.get_domaines
        if Constantes.DOMAINE_MAITRE_DES_CLES not in domaines_certificat and Constantes.DOMAINE_MESSAGES not in domaines_certificat:
            raise Exception('Mauvais certificat, pas maitre des cles / messages')
        self.__certificat_chiffrage[enveloppe.fingerprint] = CertificatChiffrage.from_enveloppe(enveloppe)

    def chiffrer_cle_secrete(self, cle_secrete: bytes):
        cles_chiffrees = dict()

        for fingerprint, cert in self.__certificat_chiffrage:
            cle_chiffree, _fingerprint = cert.enveloppe.chiffrage_asymmetrique(cle_secrete)
            cles_chiffrees[fingerprint] = cle_chiffree

        if len(cles_chiffrees) == 0:
            raise Exception("Aucuns certificats de chiffrage disponible")

        return cles_chiffrees
