import requests
import json

from os import environ

RECEPTION_HOST = environ.get('RECEPTION_HOST')

if RECEPTION_HOST is None:
    raise Exception('env param manquant : RECEPTION_HOST')


def submit_message_1():
    message_1 = {
        'destinataires': 'proprietaire',
        'contenu': """
            <p>Un message a transmettre.</p>
            <p>Test</p>
            <p>Heuille c'est pas pire, ca marche.</p>
        """,
    }

    reponse = requests.post(f'https://{RECEPTION_HOST}/message', json=message_1)
    print("Reponse : %s" % reponse.status_code)
    resultat = reponse.text
    print(resultat)
    resultat_json = json.loads(resultat)
    print(json.dumps(resultat_json, indent=2))

def main():
    submit_message_1()


if __name__ == '__main__':
    main()
