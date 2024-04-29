import requests
from os import environ

RECEPTION_HOST = environ.get('RECEPTION_HOST')

if RECEPTION_HOST is None:
    raise Exception('env param manquant : RECEPTION_HOST')


def submit_message_1():
    message_1 = {
        'nom_usager': 'proprietaire',
        'contenu': """
            <p>Un message a transmettre.</p>
            <p>Test</p>
        """,
    }

    reponse = requests.post(f'https://{RECEPTION_HOST}/message', json=message_1)
    print("Reponse : %s" % reponse.status_code)


def main():
    submit_message_1()


if __name__ == '__main__':
    main()
