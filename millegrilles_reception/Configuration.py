import argparse
import os

from typing import Optional

from millegrilles_reception import Constantes
from millegrilles_messages.messages import Constantes as ConstantesMessages

CONST_INSTANCE_PARAMS = [
    Constantes.PARAM_MQ_URL,
    Constantes.PARAM_CERT_PATH,
    Constantes.PARAM_KEY_PATH,
    ConstantesMessages.ENV_CA_PEM,
]

CONST_WEB_PARAMS = [
    Constantes.ENV_WEB_PORT,
    ConstantesMessages.ENV_CA_PEM,
    Constantes.PARAM_CERT_PATH,
    Constantes.PARAM_KEY_PATH,
]


class ConfigurationReception:

    def __init__(self):
        self.mq_url = 'https://mq:8443'

        self.cert_pem_path = '/run/secrets/cert.pem'
        self.key_pem_path = '/run/secrets/key.pem'
        self.ca_pem_path = '/run/secrets/pki.millegrille.cert'

    def get_env(self) -> dict:
        """
        Extrait l'information pertinente pour pika de os.environ
        :return: Configuration dict
        """
        config = dict()
        for opt_param in CONST_INSTANCE_PARAMS:
            value = os.environ.get(opt_param)
            if value is not None:
                config[opt_param] = value

        return config

    def parse_config(self, args: argparse.Namespace, configuration: Optional[dict] = None):
        """
        Conserver l'information de configuration
        :param args:
        :param configuration:
        :return:
        """
        dict_params = self.get_env()
        if configuration is not None:
            dict_params.update(configuration)

        mq_url = dict_params.get(Constantes.PARAM_MQ_URL)
        if mq_url == '':
            self.mq_url = None
        else:
            self.mq_url = mq_url or self.mq_url

        self.cert_pem_path = dict_params.get(Constantes.PARAM_CERT_PATH) or self.cert_pem_path
        self.key_pem_path = dict_params.get(Constantes.PARAM_KEY_PATH) or self.key_pem_path
        self.ca_pem_path = dict_params.get(ConstantesMessages.ENV_CA_PEM) or self.ca_pem_path

    def desactiver_mq(self):
        self.mq_url = None


class ConfigurationWeb:

    def __init__(self):
        self.ca_pem_path = '/run/secrets/pki.millegrille.pem'
        self.web_cert_pem_path = '/run/secrets/cert.pem'
        self.web_key_pem_path = '/run/secrets/key.pem'
        self.port = 2444

    def get_env(self) -> dict:
        """
        Extrait l'information pertinente pour pika de os.environ
        :return: Configuration dict
        """
        config = dict()
        for opt_param in CONST_WEB_PARAMS:
            value = os.environ.get(opt_param)
            if value is not None:
                config[opt_param] = value

        return config

    def parse_config(self, configuration: Optional[dict] = None):
        """
        Conserver l'information de configuration
        :param configuration:
        :return:
        """
        dict_params = self.get_env()
        if configuration is not None:
            dict_params.update(configuration)

        self.ca_pem_path = dict_params.get(ConstantesMessages.ENV_CA_PEM) or self.ca_pem_path
        self.web_cert_pem_path = dict_params.get(ConstantesMessages.ENV_CERT_PEM) or self.web_cert_pem_path
        self.web_key_pem_path = dict_params.get(ConstantesMessages.ENV_KEY_PEM) or self.web_key_pem_path
        self.port = int(dict_params.get(Constantes.ENV_WEB_PORT) or self.port)
