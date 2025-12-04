pipeline {
    // 1. CRUCIAL: Run on your specific node where Conda is installed and configured.
    agent { label 'racknerd' }

    environment {
        PYTHON = 'python'
        CONDA_ENV = 'training_camp'
        // 2. CRUCIAL: Add Conda's directory to the PATH environment variable for this pipeline.
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
                    echo "Checking workspace context..."
                    sh "pwd"
                    
                    echo "Verifying Conda environment..."
                    sh "conda run -n ${CONDA_ENV} python --version"

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
