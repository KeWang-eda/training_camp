pipeline {
    agent { label 'racknerd' }

    environment {
        PYTHON = 'python'
        CONDA_ENV = 'training_camp'
        PATH = "/home/wangke/miniconda3/bin:${env.PATH}"
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }
        stage('Evaluate All Scripts') {
            steps {
                // Now that the agent and PATH are correct, these commands will work.
                dir(env.WORKSPACE) {
                    echo "Executing the main script..."
                    sh "conda run -n ${CONDA_ENV} bash pipeline/run_all_scripts.sh"
                }
            }
        }
    }

    post {
        always {
            echo 'Pipeline finished.'
        }
        failure {
            echo 'Pipeline failed.'
        }
    }
}
