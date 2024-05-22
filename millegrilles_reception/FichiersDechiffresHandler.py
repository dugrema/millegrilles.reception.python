import asyncio
import datetime
import json
import logging
import pathlib
import shutil

import pytz
import uuid

from aiohttp import web
from aiohttp.web_request import Request
from os import makedirs, path, unlink, rename, listdir
from typing import Optional

from millegrilles_messages.messages import Constantes
from millegrilles_web import Constantes as ConstantesWeb
from millegrilles_messages.chiffrage.Mgs4 import CipherMgs4
from millegrilles_messages.chiffrage.SignatureDomaines import SignatureDomaines
from millegrilles_web.JwtUtils import creer_token_fichier, get_headers, verify


class FichiersDechiffresHandler:

    def __init__(self, web_app):
        super().__init__()
        self.__web_app = web_app
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__fichiers_thread = None
        self.__semaphore_upload_fichier = asyncio.BoundedSemaphore(value=5)

    async def setup(self):
        pass
        # dechiffres_path = f'{self.__web_app.app_path}/fichiers/dechiffres'
        # self.__web_app.app.add_routes([
        #     web.get(dechiffres_path, self.get_token_session),
        #     web.put(f'{dechiffres_path}/{{batchId}}', self.put_fichier),
        #     web.delete(f'{dechiffres_path}/{{batchId}}', self.delete_session),
        #     web.delete(f'{dechiffres_path}/{{batchId}}/{{fuuid}}', self.delete_fichier),
        # ])

    # async def get_token_session(self, request: Request):
    #     headers = {'Cache-Control': 'no-store'}
    #
    #     # Recuperer nouveau JWT
    #     user_id = 'anonymous'
    #     cle_certificat = self.__web_app.etat.clecertificat
    #
    #     # Signer un token JWT
    #     expiration = datetime.datetime.now(tz=pytz.UTC) + datetime.timedelta(days=3)
    #     uuid_batch = str(uuid.uuid4())
    #     token = creer_token_fichier(cle_certificat,
    #                                 issuer='reception', user_id=user_id, fuuid=uuid_batch, expiration=expiration)
    #
    #     reponse = {'token': token, 'batchId': uuid_batch}
    #
    #     return web.json_response(reponse, headers=headers)

    # async def put_fichier(self, request: Request):
    #     batch_id = request.match_info['batchId']
    #     reader = await request.multipart()
    #
    #     fichiers_traites = list()
    #
    #     async for field in reader:
    #         self.__logger.debug("Part recu : %s" % field.name)
    #         if field.name == 'jwt':
    #             jwt = await field.read(decode=True)
    #             jwt = jwt.decode('utf-8')
    #
    #             # Valider jwt
    #             headers_jwt = get_headers(jwt)
    #             fingerprint = headers_jwt['kid']
    #
    #             # Charger le certificat
    #             enveloppe = await self.__web_app.etat.charger_certificat(fingerprint)
    #             info_jwt = verify(enveloppe, jwt)
    #             sub = info_jwt['sub']
    #             if batch_id != sub:
    #                 return web.HTTPForbidden(reason='JWT mismatch batch_id')
    #             now = datetime.datetime.utcnow().timestamp()
    #             if info_jwt['exp'] < now:
    #                 return web.HTTPForbidden(reason='JWT Expire')
    #         elif field.name == 'files[]':
    #             fichiers_traites.append(await self.recevoir_fichier(batch_id, field))
    #         else:
    #             self.__logger.warning("PUT fichier field inconnu : %s" % field.name)
    #
    #     headers = {'Cache-Control': 'no-store'}
    #     reponse = {'fichiers': fichiers_traites}
    #     return web.json_response(reponse, headers=headers, status=201)

    async def recevoir_fichier(self, batch_id, field):
        filename = field.filename
        mimetype = field.headers['Content-Type']
        dir_staging = self.__web_app.etat.configuration.dir_staging
        path_upload = path.join(dir_staging, 'upload', batch_id)
        makedirs(path_upload, exist_ok=True)

        nom_fichier_temp = path.join(path_upload, 'upload.tmp')

        public_key_bytes = self.__web_app.etat.certificat_millegrille.get_public_x25519()

        try:
            cipher = CipherMgs4(public_key_bytes)
            format_chiffrage = 'mgs4'
            taille_dechiffre = 0
            taille_chiffre = 0
            with open(nom_fichier_temp, 'wb') as fichier:
                while True:
                    chunk = await field.read_chunk()
                    if not chunk:
                        break
                    taille_dechiffre += len(chunk)

                    chunk = cipher.update(chunk)
                    taille_chiffre += len(chunk)

                    fichier.write(chunk)
                chunk = cipher.finalize()
                taille_chiffre += len(chunk)
                fichier.write(chunk)

            enveloppes = list()
            cle_secrete = cipher.cle_secrete
            cles_chiffrees = self.__web_app.etat.chiffrer_cle_secrete(cle_secrete)
            params_dechiffrage = cipher.get_info_dechiffrage(enveloppes)

            fuuid = params_dechiffrage['hachage_bytes']
            nom_fichier = path.join(path_upload, fuuid)
            rename(nom_fichier_temp, nom_fichier)

            nom_etat = path.join(path_upload, fuuid + '.json')
            signature_domaines = SignatureDomaines.signer_domaines(cle_secrete, ['Messages'], params_dechiffrage['cle'])

            info_cle = {
                'signature': signature_domaines.to_dict(),
                'cles': cles_chiffrees,
            }
            cle_id = signature_domaines.get_cle_ref()

            commande_cles = self.__web_app.etat.formatteur_message.signer_message(
                Constantes.KIND_COMMANDE, info_cle, "MaitreDesCles", True, "ajouterCleDomaines")[0]

            now_timestamp = int(datetime.datetime.utcnow().timestamp())

            fichier_etat = {
                'cles': commande_cles,
                'cle_id': cle_id,
                'hachage': fuuid,
                'retry': 0,
                'created': now_timestamp
            }

            with open(nom_etat, 'wt') as fichier:
                json.dump(fichier_etat, fichier)

            resultat = {
                'fuuid': fuuid,
                'nom': filename,
                'mimetype': mimetype,
                'date_fichier': now_timestamp,
                'taille_dechiffre': taille_dechiffre,
                'taille_chiffre': taille_chiffre,
                'cle_id': cle_id,
                'format': format_chiffrage,
                'nonce': params_dechiffrage['header'],
            }

            return resultat
        except Exception as e:
            try:
                unlink(nom_fichier_temp)
            except FileNotFoundError:
                pass  # Ok
            raise e

        pass

    # async def delete_session(self, request: Request):
    #     headers = {'Cache-Control': 'no-store'}
    #     return web.HTTPOk()

    # async def delete_fichier(self, request: Request):
    #     headers = {'Cache-Control': 'no-store'}
    #     return web.HTTPOk()

    def cleanup_batch(self, batch_id):
        dir_staging = self.__web_app.etat.configuration.dir_staging
        path_upload = path.join(dir_staging, 'upload', batch_id)
        shutil.rmtree(path_upload, ignore_errors=True)

    async def intake_batch(self, batch_id):
        """ Pousse la batch vers l'intake de fichiers """
        dir_staging = self.__web_app.etat.configuration.dir_staging
        path_upload_batch = path.join(dir_staging, 'upload', batch_id)
        path_ready = path.join(dir_staging, 'ready')

        for nom_fichier in listdir(path_upload_batch):
            if nom_fichier.endswith(".json") is False:
                continue
            with open(path.join(path_upload_batch, nom_fichier), 'rt') as f:
                info_fichier = json.load(f)

            # Extraire transaction de cles
            cles = info_fichier['cles']
            del info_fichier['cles']

            fuuid = info_fichier['hachage']
            fichier_contenu = path.join(path_upload_batch, fuuid)
            path_destination_batch = pathlib.Path(path_ready, fuuid)
            makedirs(path_destination_batch)
            with open(path.join(path_destination_batch, ConstantesWeb.FICHIER_ETAT), 'wt') as f:
                json.dump(info_fichier, f)
            with open(path.join(path_destination_batch, ConstantesWeb.FICHIER_CLES), 'wt') as f:
                json.dump(cles, f)
            rename(fichier_contenu, path.join(path_destination_batch, '0.part'))

            # Ajouter job a l'intake de transfert
            await self.__web_app.ajouter_upload(path_destination_batch)

        shutil.rmtree(path_upload_batch)
