import os
import logging
from github import Github
from github.GithubException import GithubException

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GitHubSync:
    def __init__(self):
        self.token = os.environ.get('GITHUB_TOKEN')
        if not self.token:
            raise ValueError("GitHub token not found in environment variables")
        self.github = Github(self.token)
        
    def init_repository(self, repo_name, description="Library Management System"):
        """Initialize or get existing repository"""
        try:
            user = self.github.get_user()
            try:
                repo = user.get_repo(repo_name)
                logger.info(f"Repository {repo_name} already exists")
                return repo
            except GithubException:
                repo = user.create_repo(
                    repo_name,
                    description=description,
                    private=False,
                    has_issues=True,
                    has_wiki=True,
                    has_downloads=True
                )
                logger.info(f"Created new repository: {repo_name}")
                return repo
        except GithubException as e:
            logger.error(f"Error initializing repository: {str(e)}")
            raise

    def sync_code(self, repo_name, commit_message="Update from Library Management System"):
        """Sync current codebase with GitHub repository"""
        try:
            repo = self.github.get_user().get_repo(repo_name)
            
            # Get list of files to sync (excluding certain patterns)
            excluded_patterns = {
                '.git', '__pycache__', '.env', '.pyc',
                'venv', '.idea', '.vscode', 'node_modules'
            }
            
            for root, dirs, files in os.walk('.'):
                # Remove excluded directories
                dirs[:] = [d for d in dirs if d not in excluded_patterns]
                
                for file in files:
                    if any(pattern in file for pattern in excluded_patterns):
                        continue
                        
                    file_path = os.path.join(root, file).lstrip('./')
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            
                        try:
                            # Try to get existing file
                            github_file = repo.get_contents(file_path)
                            repo.update_file(
                                file_path,
                                commit_message,
                                content,
                                github_file.sha
                            )
                            logger.info(f"Updated file: {file_path}")
                        except GithubException:
                            # File doesn't exist, create it
                            repo.create_file(
                                file_path,
                                commit_message,
                                content
                            )
                            logger.info(f"Created file: {file_path}")
                            
                    except Exception as e:
                        logger.error(f"Error syncing file {file_path}: {str(e)}")
                        continue
                        
            return True
            
        except GithubException as e:
            logger.error(f"Error syncing code: {str(e)}")
            return False
