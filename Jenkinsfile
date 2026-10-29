pipeline {
    agent any

    environment {
        IMAGE      = 'dheeraj2105/medicare'
        TAG        = "${env.BUILD_NUMBER}"
        KUBECONFIG = '/var/lib/jenkins/.kube/config'
        NAMESPACE  = 'medicare'
    }

    options {
        buildDiscarder(logRotator(numToKeepStr: '10'))
        disableConcurrentBuilds()
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Unit Tests') {
            steps {
                sh '''
                  docker run --rm -e PYTHONDONTWRITEBYTECODE=1 -v "$WORKSPACE":/src -w /src python:3.12-slim \
                    sh -c "pip install -q -r app/requirements.txt pytest && pytest -q -p no:cacheprovider tests"
                '''
            }
        }

        stage('Build Docker Image') {
            steps {
                sh 'docker build -t $IMAGE:$TAG -t $IMAGE:latest .'
            }
        }

        stage('Push to Docker Hub') {
            steps {
                withCredentials([usernamePassword(credentialsId: 'dockerhub-creds',
                                                  usernameVariable: 'DH_USER',
                                                  passwordVariable: 'DH_PASS')]) {
                    sh '''
                      echo "$DH_PASS" | docker login -u "$DH_USER" --password-stdin
                      docker push $IMAGE:$TAG
                      docker push $IMAGE:latest
                    '''
                }
            }
        }

        stage('Deploy to Kubernetes') {
            steps {
                sh '''
                  kubectl apply -f k8s/namespace.yaml
                  kubectl apply -f k8s/pvc.yaml
                  sed -e "s|IMAGE_PLACEHOLDER|$IMAGE:$TAG|g" -e "s|VERSION_PLACEHOLDER|$TAG|g" k8s/deployment.yaml | kubectl apply -f -
                  kubectl apply -f k8s/service.yaml
                  kubectl -n $NAMESPACE rollout status deployment/medicare --timeout=180s
                  kubectl -n $NAMESPACE get pods,svc -o wide
                '''
            }
        }

        stage('Smoke Test') {
            steps {
                sh '''
                  NODE_IP=$(hostname -I | awk '{print $1}')
                  for i in 1 2 3 4 5 6; do
                    curl -fsS http://$NODE_IP:30080/health && exit 0
                    sleep 5
                  done
                  exit 1
                '''
            }
        }
    }

    post {
        success {
            echo "Deployed ${env.IMAGE}:${env.TAG} -> open http://<EC2-PUBLIC-IP>:30080"
        }
        always {
            sh 'docker logout || true; docker image prune -f || true'
        }
    }
}
