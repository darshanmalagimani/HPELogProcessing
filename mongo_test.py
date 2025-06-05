#!/usr/bin/env python3
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
import sys

def test_mongodb_connection():
    # Load environment variables
    load_dotenv()
    
    # Get MongoDB connection details
    mongo_user = quote_plus(os.getenv("MONGO_USER"))
    mongo_pass = quote_plus(os.getenv("MONGO_PASS"))
    mongo_host = os.getenv("MONGO_HOST", "localhost")
    mongo_port = os.getenv("MONGO_PORT", "27017")
    mongo_db = os.getenv("MONGO_DB", "log_analysis_db")
    
    # Construct connection string
    mongo_uri = f"mongodb://{mongo_user}:{mongo_pass}@{mongo_host}:{mongo_port}/"
    
    print(f"Attempting to connect to MongoDB at {mongo_host}:{mongo_port}")
    print(f"Using database: {mongo_db}")
    print(f"Using username: {mongo_user}")
    
    try:
        # Try to connect with a short timeout
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        
        # The ismaster command is cheap and does not require auth
        client.admin.command('ismaster')
        
        # If we get here, we can successfully connect
        print("Successfully connected to MongoDB!")
        
        # Try to access the database
        db = client[mongo_db]
        print(f"Successfully accessed database: {mongo_db}")
        
        # List collections to verify permissions
        collections = db.list_collection_names()
        print(f"Available collections: {collections}")
        
        # Try to insert a test document
        test_collection = db['test_connection']
        result = test_collection.insert_one({"test": "connection", "timestamp": "test"})
        print(f"Successfully inserted test document with ID: {result.inserted_id}")
        
        # Clean up test document
        test_collection.delete_one({"_id": result.inserted_id})
        print("Successfully cleaned up test document")
        
        return True
        
    except ConnectionFailure as e:
        print(f"Failed to connect to MongoDB. Error: {e}")
        return False
    except ServerSelectionTimeoutError as e:
        print(f"Server selection timeout. Error: {e}")
        return False
    except Exception as e:
        print(f"Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_mongodb_connection()
    sys.exit(0 if success else 1)

