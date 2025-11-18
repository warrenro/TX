｀#!/bin/bash

# Function to create a default .gitignore if it doesn't exist
create_gitignore_if_needed() {
    if [ ! -f .gitignore ]; then
        echo "找不到 .gitignore 檔案，正在為 Python 專案建立預設檔案。"
        cat <<EOL > .gitignore
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# PyInstaller
#  Usually these files are written by a python script from a template
#  before PyInstaller builds the exe, so as to inject date/other infos into it.
*.manifest
*.spec

# Installer logs
pip-log.txt
pip-delete-this-directory.txt

# Unit test / coverage reports
htmlcov/
.tox/
.nox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
.hypothesis/
.pytest_cache/

# Environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# Spyder project settings
.spyderproject
.spyderworkspace

# Rope project settings
.ropeproject

# mkdocs documentation
/site

# mypy
.mypy_cache/
.dmypy.json
dmypy.json

# Jupyter Notebook
.ipynb_checkpoints

# IDE settings
.idea/
.vscode/
*.swp
*~
EOL
    fi
}

# Function to move YAML files to .github/workflows
move_yaml_files() {
    if [ -d .github/workflows ]; then
        echo ".github/workflows 目錄已存在。"
    else
        echo "正在建立 .github/workflows 目錄。"
        mkdir -p .github/workflows
    fi

    # Check if there are any .yml files in the root directory
    if ls *.yml 1> /dev/null 2>&1; then
        echo "正在將根目錄的 .yml 檔案移動到 .github/workflows/"
        mv *.yml .github/workflows/
    else
        echo "根目錄中找不到 .yml 檔案。"
    fi
}

# Function to set up git remote if it doesn't exist
setup_git_repo() {
    # 1. Initialize git if not already done
    if [ ! -d .git ]; then
        echo "正在初始化 Git 儲存庫..."
        git init
    fi

    # 2. Check for remote 'origin' and add if it's missing
    if ! git remote -v | grep -q "origin"; then
        echo "找不到遠端儲存庫 'origin'。"
        read -p "請輸入您的 GitHub 使用者名稱: " github_username
        if [ -z "$github_username" ]; then
            echo "GitHub 使用者名稱不能為空。正在中止操作。"
            exit 1
        fi
        
        # The script assumes the directory name is the repo name
        repo_name=$(basename "$PWD")
        git_url="https://github.com/$github_username/$repo_name.git"
        
        echo "--------------------------------------------------"
        echo "腳本將新增以下遠端儲存庫 URL："
        echo "$git_url"
        echo "請確認此 URL 是否正確 (這需要您的目錄名稱 '$repo_name' 與 GitHub 上的儲存庫名稱一致)。"
        echo "--------------------------------------------------"
        read -p "是否正確？ (y/n): " confirm
        
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            echo "操作已中止。請手動設定遠端儲存庫：git remote add origin <YOUR_URL>"
            exit 1
        fi
        
        git remote add origin "$git_url"
        echo "已新增遠端 'origin': $git_url"
    fi
}

# --- Main Script ---

# Setup repository (init and remote)
setup_git_repo

create_gitignore_if_needed
move_yaml_files

# Add all changes
git add .

# Commit with a message
read -p "請輸入提交訊息 (commit message): " commit_message
if [ -z "$commit_message" ]; then
    commit_message="Update project files" # Default commit message
fi
git commit -m "$commit_message"

# Push to the remote repository
current_branch=$(git rev-parse --abbrev-ref HEAD)
read -p "請輸入要推送的分支名稱 (預設為: $current_branch): " branch_name
if [ -z "$branch_name" ]; then
    branch_name=$current_branch
fi
git push origin "$branch_name"

echo "程式碼已成功推送到 GitHub！"
