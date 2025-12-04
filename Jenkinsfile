pipeline {
    agent any

    environment {
        PYTHON = 'python'
        CONDA_ENV = 'training_camp'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }
        stage('Evaluate All Scripts') {
            steps {
                // Run inside conda environment after ensuring workspace has the latest code
                dir(env.WORKSPACE) {
                    // Step 1: Sanity check workspace context
                    sh "conda run -n ${CONDA_ENV} bash -lc 'pwd'"
                    // Step 2: Execute the pipeline script
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
