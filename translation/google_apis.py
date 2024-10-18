import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes pour accéder à Google Docs et Google Drive
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


# Fonction pour s'authentifier sur Google API
def google_authenticate():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "google_credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=8080)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds


# Fonction pour vérifier si le document existe déjà dans un dossier Google Drive
def document_exists(service_drive, folder_id, document_title):
    # Échapper correctement les guillemets simples (apostrophes) dans le titre
    escaped_title = document_title.replace("'", "\\'")

    # Construire la requête pour chercher un fichier avec le même nom dans le dossier
    query = f"'{folder_id}' in parents and name = '{escaped_title}' and mimeType = 'application/vnd.google-apps.document'"

    # Exécuter la requête
    results = service_drive.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])

    # Vérification de l'existence du fichier
    if files:
        print(f"Le document '{document_title}' existe déjà dans le dossier.")
        return True
    return False


# Fonction pour créer un document Google Docs dans un dossier spécifique
def create_google_doc(service_docs, service_drive, folder_id, document_title, content):
    # Créer le document seulement s'il n'existe pas
    if not document_exists(service_drive, folder_id, document_title):
        document = {"title": document_title}
        doc = service_docs.documents().create(body=document).execute()
        document_id = doc["documentId"]

        # Déplacer le document dans le dossier spécifié
        file = service_drive.files().get(fileId=document_id, fields="parents").execute()
        previous_parents = ",".join(file.get("parents"))
        service_drive.files().update(
            fileId=document_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields="id, parents",
        ).execute()

        # Ajouter le contenu au document
        requests = [
            {
                "insertText": {
                    "location": {
                        "index": 1,
                    },
                    "text": content,
                }
            }
        ]
        service_docs.documents().batchUpdate(
            documentId=document_id, body={"requests": requests}
        ).execute()
        print(f"Document '{document_title}' créé avec succès dans le dossier.")
    else:
        print(f"Document '{document_title}' non créé car il existe déjà.")


def save_df_to_gdrive(creds, df, lang_code):
    service_docs = build("docs", "v1", credentials=creds)
    service_drive = build("drive", "v3", credentials=creds)

    if lang_code == "es":
        folder_id = "1KpNvszabc4KuI0AXbaA-dKuDdSQFeYsW"
        # "1yqvCEsF55Zntbc__Oz89-mCgvBO0GRIj"
    if lang_code == "en":
        folder_id = "1KpNvszabc4KuI0AXbaA-dKuDdSQFeYsW"
        "1YCSmqQtV41IDWcABtxG_ADO-TWynCtlX"

    for index, row in df.iterrows():
        # Create document with original title and content
        doc_title = f"{row['id']}_{row['title']}"
        doc_content = row["content"]

        # Créer un document Google Docs dans le dossier spécifié
        create_google_doc(
            service_docs, service_drive, folder_id, doc_title, doc_content
        )

        # Create document with translated title and content
        doc_title_translated = f"{row['id']}_{row['title_' + lang_code]}"
        doc_content_translated = row["content_" + lang_code]

        # Créer un document Google Docs dans le dossier spécifié
        create_google_doc(
            service_docs,
            service_drive,
            folder_id,
            doc_title_translated,
            doc_content_translated,
        )


def get_files_by_docid_prefix(service_drive, docid, old_folder_id):
    """
    Recherche tous les fichiers dans 'old_folder_id' dont le nom commence par 'docid_'.

    :param service_drive: Service Google Drive authentifié.
    :param docid: Le docid à rechercher (ex: 45).
    :param old_folder_id: ID du dossier source où rechercher les fichiers.
    :return: Une liste de fichiers (ID et nom) correspondant au critère de recherche.
    """
    try:
        # Construire la requête pour chercher les fichiers dont le nom commence par 'docid_'
        query = f"name contains '{docid}_' and mimeType = 'application/vnd.google-apps.document' and '{old_folder_id}' in parents"
        print(query)
        # Exécuter la requête
        results = (
            service_drive.files().list(q=query, fields="files(id, name)").execute()
        )
        files = results.get("files", [])

        # Afficher les fichiers trouvés
        if files:
            for file in files:
                print(f"Fichier trouvé: {file['name']} (ID: {file['id']})")
            return files
        else:
            print(
                f"Aucun fichier trouvé avec le préfixe '{docid}_' dans le dossier {old_folder_id}."
            )
            return None
    except Exception as e:
        print(f"Erreur lors de la recherche des fichiers : {e}")
        return None


def move_file(service_drive, file_id, old_folder_id, new_folder_id):
    """
    Déplace un fichier de 'old_folder_id' vers 'new_folder_id' sur Google Drive.

    :param service_drive: Service Google Drive authentifié.
    :param file_id: ID du fichier à déplacer.
    :param old_folder_id: ID du dossier source.
    :param new_folder_id: ID du dossier destination.
    """
    try:
        # Ajouter le fichier au nouveau dossier
        file = service_drive.files().get(fileId=file_id, fields="parents").execute()
        previous_parents = ",".join(file.get("parents"))

        # Déplacer le fichier en ajoutant le nouveau dossier et en supprimant l'ancien
        service_drive.files().update(
            fileId=file_id,
            addParents=new_folder_id,
            removeParents=old_folder_id,
            fields="id, parents",
        ).execute()

        print(
            f"Le fichier avec l'ID {file_id} a été déplacé dans le dossier {new_folder_id}."
        )
    except Exception as e:
        print(f"Erreur lors du déplacement du fichier {file_id} : {e}")


# Utilisation des fonctions
def move_files_by_docid(creds, docid, lang_code):
    """
    Trouve et déplace tous les fichiers dont le nom commence par 'docid_' d'un ancien dossier à un nouveau.

    :param creds: Credentials d'authentification Google.
    :param docid: Le docid à rechercher.
    :param old_folder_id: ID du dossier source.
    :param new_folder_id: ID du dossier de destination.
    """

    if lang_code == "es":
        old_folder_id = "1KpNvszabc4KuI0AXbaA-dKuDdSQFeYsW"
        # "1yqvCEsF55Zntbc__Oz89-mCgvBO0GRIj"
        new_folder_id = "1DHIycvGv7H5Jtfdempe_Y7455pIxnWrN"
    if lang_code == "en":
        old_folder_id = "1KpNvszabc4KuI0AXbaA-dKuDdSQFeYsW"
        "1YCSmqQtV41IDWcABtxG_ADO-TWynCtlX"
        new_folder_id = "1DHIycvGv7H5Jtfdempe_Y7455pIxnWrN"

    # Initialiser le service Google Drive
    service_drive = build("drive", "v3", credentials=creds)

    # Récupérer les fichiers avec le préfixe 'docid_'
    files = get_files_by_docid_prefix(service_drive, docid, old_folder_id)
    print(files)

    # Si des fichiers sont trouvés, les déplacer
    if files:
        for file in files:
            move_file(service_drive, file["id"], old_folder_id, new_folder_id)
