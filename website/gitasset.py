import os, requests, json

class GitAsset:
    def __init__(self, repo, owner='rookwoodirl'):
        # initialize where we're dropping files
        self.path = os.path.join('website', 'static', 'gitrepos', repo)
        if not os.path.isdir(self.path):
            print(f'Making dir for repo: {repo}')
            os.makedirs(self.path)

        # some variables about the git repo...
        self.owner = owner
        self.repo = repo

        # track meta data related to the files to detect updates
        self.files = {}
        self.update()

    def update(self):
        new_info = self.get_remote_files_info()

        for new_file in new_info:
            if new_file not in self.files or new_info[new_file]['sha'] != self.files[new_file]['sha']: # file was updated since we last saw!
                print(f'Getting {self.repo}.{new_file}...')
                self.get_remote_file(new_file)
                self.files[new_file] = new_info[new_file]

    def get_remote_files_info(self):
        """
        returns the files in the main branch of this objects Git repo
        by convention, files should be exposed in public/ directory
        """
        response = requests.get(f'https://api.github.com/repos/{self.owner}/{self.repo}/contents/public')
        content = json.loads(response.content)

        # return information about files to download
        out = {} # could do this in-line, but it's not very readable
        for file_info in content:
            fname = file_info['path'][len('public/'):] # truncate public off the front
            url = file_info['download_url']
            sha = file_info['sha']

            out[fname] = { 'url' : url, 'sha' : sha}
        return out

    def get_remote_file(self, file):
        # get the data
        url = f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/main/public/{file}"
        response = requests.get(url)

        # write it out
        path = os.path.join(self.path, file)
        with open(path, "wb+") as file:
            file.write(response.content)

