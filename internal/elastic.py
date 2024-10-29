import os
from typing import Annotated

from dotenv import load_dotenv
from elasticsearch import Elasticsearch
from fastapi import Depends


# Load Environment Variables.
load_dotenv()

ELASTICSEARCH_URL = os.getenv('ELASTICSEARCH_URL')
ELASTICSEARCH_API_KEY = os.getenv('ELASTICSEARCH_API_KEY')

# Initialize Elasticsearch client.
es_client = Elasticsearch(
    hosts=ELASTICSEARCH_URL,
    api_key=ELASTICSEARCH_API_KEY
)


def get_es_client():
    return es_client


# Common dependencies.
ESClientDep = Annotated[Elasticsearch, Depends(get_es_client)]
