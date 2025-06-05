#!/usr/bin/env python3
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from urllib.parse import quote_plus
import json

def verify_mongodb_data():
    # Load environment variables
    load_dotenv()
    
    # Get MongoDB connection details
    mongo_user = quote_plus(os.getenv("MONGO_USER"))
    mongo_pass = quote_plus(os.getenv("MONGO_PASS"))
    mongo_host = os.getenv("MONGO_HOST", "localhost")
    mongo_port = os.getenv("MONGO_PORT", "27017")
    mongo_db = os.getenv("MONGO_DB", "log_analysis_db")
    collection_name = "CSFE-65658_component_failure_HPE_SR_Gen10"
    
    # Connect to MongoDB
    mongo_uri = f"mongodb://{mongo_user}:{mongo_pass}@{mongo_host}:{mongo_port}/"
    client = MongoClient(mongo_uri)
    db = client[mongo_db]
    
    print(f"\nChecking MongoDB database: {mongo_db}")
    print(f"Collection: {collection_name}")
    
    # Get the collection
    collection = db[collection_name]
    
    # Count documents
    doc_count = collection.count_documents({})
    print(f"\nFound {doc_count} documents in collection")
    
    # Get the most recent document
    if doc_count > 0:
        latest_doc = collection.find_one({}, sort=[('_id', -1)])
        print("\nMost recent document:")
        print(json.dumps(latest_doc, indent=2, default=str))
    else:
        print("\nNo documents found in the collection")
    
    client.close()

if __name__ == "__main__":
    verify_mongodb_data()

