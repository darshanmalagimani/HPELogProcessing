pipeline {
    agent { label 'python313' }

    environment {
        // Secure credentials
        MINIO_ACCESS_KEY = credentials('minio-access-key-id')
        MINIO_SECRET_KEY = credentials('minio-secret-key-id')
        MONGO_USER       = credentials('mongo-user')
        MONGO_PASS       = credentials('mongo-pass')

        // Non-secret configuration
        MONGO_HOST       = 'mongodb.phazite.space'
        MONGO_PORT       = '27017'
        MONGO_DB         = 'log_analysis_db'
        MINIO_ENDPOINT   = 'minio-access.phazite.space'
        MINIO_SECURE     = 'True'
    }

    triggers {
        GenericTrigger(
            genericVariables: [
                [key: 'key', value: '$.Records[0].s3.object.key'],
                [key: 'bucket', value: '$.Records[0].s3.bucket.name']
            ],
            causeString: 'MinIO object upload detected',
            token: 'minio-trigger',
            printContributedVariables: true,
            printPostContent: true
        )
    }

    stages {
        stage('Clone GitHub Repo') {
            steps {
                git(
                    url: 'https://github.com/darshanmalagimani/HPELogProcessing.git',
                    credentialsId: 'git-credentials'
                )
            }
        }

        stage('Prepare Directories') {
            steps {
                sh '''
                    mkdir -p machines
                    mkdir -p output
                    mkdir -p processed
                '''
            }
        }

        stage('Download Object from MinIO') {
            steps {
                sh '''
                    curl https://dl.min.io/client/mc/release/linux-amd64/mc -o mc
                    chmod +x mc
                    ./mc alias set myminio http://${MINIO_ENDPOINT} ${MINIO_ACCESS_KEY} ${MINIO_SECRET_KEY}
                    ./mc cp myminio/${bucket}/${key} machines/
                '''
            }
        }

        stage('Run client.py') {
            steps {
                sh 'python3 client.py'
            }
        }

        stage('Run master.py using .venv') {
            steps {
                sh '''
                    . .venv/bin/activate
                    python master.py
                '''
            }
        }

        stage('Zip output and processed') {
            steps {
                sh 'zip -r results.zip output processed || true'
            }
        }

        stage('Archive Results') {
            steps {
                archiveArtifacts artifacts: 'results.zip', fingerprint: true
            }
        }

        stage('Cleanup .venv') {
            steps {
                sh 'rm -rf .venv'
            }
        }
    }

    post {
        always {
            echo 'Pipeline execution completed.'
        }
        failure {
            echo 'Pipeline failed.'
        }
    }
}
