pipeline {
    agent any

    environment {
        PROJECT_ROOT = '/home/wangke/ByteDance/training_camp'
        PYTHON = 'python'
        CONDA_ENV = 'training_camp'
    }

    stages {
        stage('Evaluate All Scripts') {
            steps {
                // Run inside conda environment without altering global shell
                sh "conda run -n ${CONDA_ENV} bash -lc '${PROJECT_ROOT}/pipeline/run_all_scripts.sh'"
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
