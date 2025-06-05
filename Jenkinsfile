pipeline {
    agent { label 'python313' }

    environment {
        // Secure credentials (use IDs from Jenkins credentials store)
        MINIO_ACCESS_KEY = credentials('minio-access-key-id')
        MINIO_SECRET_KEY = credentials('minio-secret-key-id')
        MONGO_USER = credentials('mongo-user-id')
        MONGO_PASS = credentials('mongo-pass-id')

        // Non-secret env variables
        MONGO_HOST = 'mongodb.phazite.space'
        MONGO_PORT = '27017'
        MONGO_DB = 'log_analysis_db'

        MINIO_ENDPOINT = 'minio-access.phazite.space'
        MINIO_SECURE = 'True'
    }

    triggers {
        // Poll Git repository every 1 minute for changes (for example, new folder in machines/)
        pollSCM('* * * * *')
    }

    options {
        timestamps()
        timeout(time: 30, unit: 'MINUTES')  // Adjust if your jobs take longer
    }

    stages {
        stage('Checkout') {
            steps {
                echo '📥 Checking out code...'
                checkout scm
                sh 'ls -la'
            }
        }

        stage('Prepare Directories') {
            steps {
                echo '📂 Creating required directories...'
                sh '''
                    mkdir -p output
                    mkdir -p processed
                    echo "✅ Folders 'output' and 'processed' are ready."
                '''
            }
        }

        stage('Run Old Client') {
            steps {
                echo '🚀 Running oldclient.py to set up environment and preprocessing...'
                sh 'python3.13 oldclient.py'
            }
        }

        stage('Run Master Script') {
            steps {
                echo '🧠 Running master.py for processing and MinIO/MongoDB upload...'
                sh 'python3.13 master.py'
            }
        }
    }

    post {
        always {
            echo '🌀 Pipeline completed (success or fail).'
        }
        success {
            echo '✅ Jenkins pipeline finished successfully.'
        }
        failure {
            echo '❌ Jenkins pipeline failed.'
        }
    }
}
