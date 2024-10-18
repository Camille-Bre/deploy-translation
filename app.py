import csv
import os
from datetime import datetime

import pandas as pd
from flask import Flask, flash, redirect, render_template, request, session, url_for
from openai import OpenAI

from translation.google_apis import (
    google_authenticate,
    move_files_by_docid,
    save_df_to_gdrive,
)
from translation.translation import translate_csv_column

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Chemin des fichiers CSV
CSV_FILE = "./data/translation_followup_test.csv"
USERS_FILE = "./data/users.csv"
CONTENT_FILE = "./data/posts.csv"

# Initialize the OpenAI API
api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api_key)


# Fonction pour charger les articles
def load_articles():
    return pd.read_csv(CSV_FILE)


# Fonction pour sauvegarder les articles
def save_articles(df):
    df.to_csv(CSV_FILE, index=False)


# Fonction pour charger les utilisateurs
# def load_users():
#     users_df = pd.read_csv(USERS_FILE)
#     users_df["lang"] = users_df["lang"].fillna(
#         "en"
#     )  # Mettre 'en' par défaut si la langue est vide
#     return users_df


def get_user_by_username(username):
    # Ouvrir et lire le fichier users.csv
    with open(USERS_FILE, mode="r") as file:
        reader = csv.DictReader(file)
        # Parcourir chaque ligne pour trouver l'utilisateur
        for row in reader:
            if row["username"] == username:
                # Retourner un dictionnaire contenant les informations de l'utilisateur
                return {
                    "username": row["username"],
                    "role": row["role"],
                    "lang": row["lang"],
                }
    # Retourner None si l'utilisateur n'est pas trouvé
    return None


# Page de connexion
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]

        # Charger les utilisateurs
        user = get_user_by_username(username)

        if user:
            session["username"] = username
            session["role"] = user["role"]
            session["lang"] = user["lang"]

            # Redirection en fonction du rôle
            if user["role"] == "admin":
                return redirect(url_for("admin_dashboard"))
            elif user["role"] == "translator":
                return redirect(url_for("select_language"))
            elif user["role"] == "reviewer":
                return redirect(url_for("reviewer_dashboard"))
            elif user["role"] == "approver":
                return redirect(url_for("approver_dashboard"))

    return render_template("login.html")


@app.route("/admin_dashboard")
def admin_dashboard():
    # Vérifier que l'utilisateur est connecté et a le rôle d'admin
    if "username" not in session or session["role"] != "admin":
        return redirect(url_for("login"))

    # Rendre la page de l'admin avec les trois boutons
    return render_template("admin_dashboard.html")


@app.route("/select_language", methods=["GET", "POST"])
def select_language():
    if request.method == "POST":
        lang = request.form["language"]
        session["lang"] = lang  # Enregistrer la langue choisie dans la session
        return redirect(url_for("translator_dashboard"))

    return render_template("select_language.html")


@app.route("/translator_dashboard", methods=["GET", "POST"])
def translator_dashboard():
    # Vérifier que l'utilisateur est connecté et a le rôle de traducteur
    if "username" not in session or session["role"] not in ["admin", "translator"]:
        return redirect(url_for("login"))

    # Charger les articles depuis le fichier CSV
    articles_df = load_articles()

    # Filtrer les articles en fonction de la langue choisie
    lang = session.get("lang")
    print(lang)
    ai_translated_column = "ai_translated_" + lang
    to_translate_column = "to_be_translated_" + lang

    # Sélectionner les articles qui n'ont pas encore été traduits et qui doivent être traduits
    articles_to_translate = articles_df[
        (articles_df[ai_translated_column] == False)
        & (articles_df[to_translate_column] == True)
    ]

    # Ordonner les articles par ID
    articles_to_translate = articles_to_translate.sort_values(by="id")

    if request.method == "POST":
        selected_articles = request.form.getlist("articles")
        selected_articles = list(map(int, selected_articles))
        # Ici vous pouvez ajouter la logique pour traduire les articles sélectionnés
        # Récupérer les articles sélectionnés et retrouver les contenus dans le fichier CSV
        posts_df = pd.read_csv(CONTENT_FILE)
        selected_posts = posts_df[posts_df["id"].isin(selected_articles)]

        # Traduire les colonnes "title" et "content" du DataFrame
        source_language_code = "fr"
        target_language_code = lang
        model_name = "gpt-4o"

        df_translated = translate_csv_column(
            selected_posts,
            ["title", "content"],
            client,
            source_language_code,
            target_language_code,
            model_name,
            temperature=0,
        )

        # Sauvegarder les traductions dans un fichier CSV avec nom unique
        output_file = f"./data/posts_translated_{target_language_code}_{session['username']}_{datetime.now().strftime('%d%m%y_%H%M%S')}.csv"

        # Changer la colonne "to_translate" à False pour les articles traduits dans le fichier CSV
        articles_df.loc[
            articles_df["id"].isin(selected_articles), to_translate_column
        ] = False

        # Change the "ai_translated" column to True for the translated articles in the CSV file
        articles_df.loc[
            articles_df["id"].isin(selected_articles), ai_translated_column
        ] = True

        # Sauvegarder les traductions dans google docs
        try:
            creds = google_authenticate()
            save_df_to_gdrive(creds, df_translated, lang)

            flash("Traduction effectuée avec succès.", "success")

            # Sauvegarder le fichier CSV mis à jour
            save_articles(articles_df)

        except Exception as e:
            flash(f"Erreur lors de la traduction : {str(e)}", "danger")

        return redirect(url_for("translator_dashboard"))

    return render_template("translator_dashboard.html", articles=articles_to_translate)


@app.route("/reviewer_dashboard", methods=["GET", "POST"])
def reviewer_dashboard():
    # Vérifier que l'utilisateur est connecté et a le rôle de reviewer
    if "username" not in session or session["role"] not in ["admin", "reviewer"]:
        return redirect(url_for("login"))

    # Charger les articles depuis le fichier .csv
    articles_df = load_articles()

    # Filtrer les articles en fonction de la langue choisie
    lang = session.get("lang")
    ai_translated_column = "ai_translated_" + lang
    translation_reviewed_column = "translation_reviewed_" + lang

    # Sélectionner les articles déja traduits par IA par encore reviewé
    articles_to_review = articles_df[
        (articles_df[ai_translated_column] == True)
        & (articles_df[translation_reviewed_column] == False)
    ]

    # Ordonner les articles par ID
    articles_to_review = articles_to_review.sort_values(by="id")

    if request.method == "POST":
        selected_articles = request.form.getlist("articles")
        selected_articles = list(map(int, selected_articles))

        try:
            creds = google_authenticate()
            for docid in selected_articles:
                move_files_by_docid(creds, docid, lang)

            flash("Review validée et documents déplacés.", "success")

            # Sauvegarder le fichier CSV mis à jour
            save_articles(articles_df)

        except Exception as e:
            flash(f"Erreur lors du déplacement des documents : {str(e)}", "danger")

        return redirect(url_for("reviewer_dashboard"))
    return render_template("reviewer_dashboard.html", articles=articles_to_review)


@app.route("/approver_dashboard", methods=["GET", "POST"])
def approver_dashboard():
    # Code pour afficher le dashboard des approbateurs
    pass


# Tableau de bord : affichage de tous les articles
# Tableau de bord : affichage des articles filtrés en fonction du rôle et de la langue
@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    df = load_articles()

    # Filtrer les articles selon le rôle et la langue de l'utilisateur
    role = session["role"]
    filtered_articles = None

    if role == "translator":
        if session["lang"] == "en":
            filtered_articles = df[
                df["ai_translated_en"] == False
            ]  # Articles pas encore traduits en anglais
        elif session["lang"] == "es":
            filtered_articles = df[
                df["ai_translated_es"] == False
            ]  # Articles pas encore traduits en espagnol

    elif role == "reviewer":
        if session["lang"] == "en":
            filtered_articles = df[
                df["translation_reviewed_en"] == False
            ]  # Articles pas encore révisés en anglais
        elif session["lang"] == "es":
            filtered_articles = df[
                df["translation_reviewed_es"] == False
            ]  # Articles pas encore révisés en espagnol

    elif role == "approver":
        if session["lang"] == "en":
            filtered_articles = df[
                df["approved_en"] == False
            ]  # Articles pas encore approuvés en anglais
        elif session["lang"] == "es":
            filtered_articles = df[
                df["approved_es"] == False
            ]  # Articles pas encore approuvés en espagnol

    # Si un formulaire POST a été soumis
    if request.method == "POST":
        selected_articles = request.form.getlist(
            "article_ids"
        )  # Obtenir les articles sélectionnés
        for article_id in selected_articles:
            article_id = int(article_id)

            # Effectuer l'action en fonction du rôle
            if role == "translator":
                if session["lang"] == "en":
                    df.loc[df["id"] == article_id, "ai_translated_en"] = True
                elif session["lang"] == "es":
                    df.loc[df["id"] == article_id, "ai_translated_es"] = True

            elif role == "reviewer":
                if session["lang"] == "en":
                    df.loc[df["id"] == article_id, "translation_reviewed_en"] = True
                    df.loc[df["id"] == article_id, "translation_reviewed_by_en"] = (
                        session["username"]
                    )
                elif session["lang"] == "es":
                    df.loc[df["id"] == article_id, "translation_reviewed_es"] = True
                    df.loc[df["id"] == article_id, "translation_reviewed_by_es"] = (
                        session["username"]
                    )

            elif role == "approver":
                if session["lang"] == "en":
                    df.loc[df["id"] == article_id, "approved_en"] = True
                    df.loc[df["id"] == article_id, "approved_by_en"] = session[
                        "username"
                    ]
                elif session["lang"] == "es":
                    df.loc[df["id"] == article_id, "approved_es"] = True
                    df.loc[df["id"] == article_id, "approved_by_es"] = session[
                        "username"
                    ]

        # Sauvegarder les changements dans le CSV
        save_articles(df)

        flash("Les articles sélectionnés ont été mis à jour.")
        return redirect(url_for("dashboard"))

    return render_template(
        "dashboard.html", articles=filtered_articles.to_dict(orient="records")
    )


# Détails d'un article spécifique
@app.route("/article/<int:article_id>", methods=["GET", "POST"])
def article(article_id):
    if "username" not in session:
        return redirect(url_for("login"))

    df = load_articles()
    article = df[df["id"] == article_id].iloc[0]

    if request.method == "POST":
        role = session["role"]
        username = session["username"]

        # Actions en fonction du rôle
        if role == "translator":
            if "translate_en" in request.form:
                df.loc[df["id"] == article_id, "ai_translated_en"] = True
            elif "translate_es" in request.form:
                df.loc[df["id"] == article_id, "ai_translated_es"] = True

        if role == "reviewer":
            if "review_en" in request.form:
                df.loc[df["id"] == article_id, "translation_reviewed_en"] = True
                df.loc[df["id"] == article_id, "translation_reviewed_by_en"] = username
            elif "review_es" in request.form:
                df.loc[df["id"] == article_id, "translation_reviewed_es"] = True
                df.loc[df["id"] == article_id, "translation_reviewed_by_es"] = username

        if role == "approver":
            if "approve_en" in request.form:
                df.loc[df["id"] == article_id, "approved_en"] = True
                df.loc[df["id"] == article_id, "approved_by_en"] = username
            elif "approve_es" in request.form:
                df.loc[df["id"] == article_id, "approved_es"] = True
                df.loc[df["id"] == article_id, "approved_by_es"] = username

        save_articles(df)
        return redirect(url_for("dashboard"))

    return render_template("article.html", article=article)


# Déconnexion
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
