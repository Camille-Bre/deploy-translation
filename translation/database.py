import os

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# Connexion to database
def connect_to_db(db_url: str) -> tuple:
    engine = create_engine(db_url)
    session_maker = sessionmaker(bind=engine)
    return engine, session_maker


# Load data from CMS database
def load_data_from_db(
    table_name: str,
    engine: create_engine,
    session_maker: sessionmaker,
    interval: str = None,
) -> pd.DataFrame:
    session = session_maker()
    if interval:
        query = f"SELECT * FROM {table_name} WHERE created_at >= NOW() - INTERVAL '{interval}'"
    else:
        query = f"SELECT * FROM {table_name}"
    df = pd.read_sql_query(query, engine)
    session.close()
    return df


def get_posts_from_titles(df) -> pd.DataFrame:
    # Get the posts from the db
    CMS_DB_URL = (
        "postgresql://"
        + os.getenv("CMS_DB_USER")
        + ":"
        + os.getenv("CMS_DB_PWD")
        + "@"
        + os.getenv("CMS_DB_HOST")
        + ":"
        + os.getenv("CMS_DB_PORT")
        + "/"
        + os.getenv("CMS_DB_NAME")
    )
    cms_engine, cms_session_maker = connect_to_db(CMS_DB_URL)

    posts_df = load_data_from_db("posts", cms_engine, cms_session_maker)

    # ONly keep the posts with the title in the df
    posts_df = posts_df[posts_df["title"].isin(df["title"].values)]

    # Keep only the columns we need
    posts_df = posts_df[["id", "title", "content"]]

    # Save the posts in a csv file
    posts_df.to_csv("./data/posts.csv", index=False)

    return posts_df
