pipeline {
    agent any  // 任意可用的 Jenkins 节点执行（无需指定特定节点，最简单配置）
    stages {
        // 单个阶段：仅打印触发提示
        stage('触发识别') {
            steps {
                // 核心逻辑：打印提示信息
                echo "✅ Jenkins Pipeline 已识别到触发！触发成功～"
            }
        }
    }
}
