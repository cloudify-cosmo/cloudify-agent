param($VERSION,$PRERELEASE,$DEV_BRANCH)

function resolve_current_build_branch_urls() {
    echo "### Resolve current build branch urls ###"
    $env:AWS_S3_PATH = "s3://cloudify-release-eu/cloudify/$VERSION/$PRERELEASE-build"
    $env:current_branch = "master"

    if ($DEV_BRANCH -ne "" -And $DEV_BRANCH -ne "master") {
        $branch_exists = $( git rev-parse --verify --quiet $DEV_BRANCH )
        if ($branch_exists -ne "") {
            $env:current_branch = $DEV_BRANCH
            $env:AWS_S3_PATH = "$env:AWS_S3_PATH/$env:current_branch"
        }
    }

    # Required urls
    $env:DEV_REQUIREMENTS_URL = "https://raw.githubusercontent.com/cloudify-cosmo/cloudify-agent/$env:current_branch/dev-requirements.txt"
    $env:REPO_ZIP_URL = "https://github.com/cloudify-cosmo/cloudify-agent/archive/$env:current_branch.zip"

    echo "Chosen branch to build from $env:current_branch."
}


function preparation () {
    echo "### Preparation ###"
    pip install wheel

    echo "dev requirement url of the agent $env:DEV_REQUIREMENTS_URL"
    echo "Path to ziped repo of the agent $env:REPO_ZIP_URL"
    pip wheel --wheel-dir packaging/source/wheels --requirement $env:DEV_REQUIREMENTS_URL
    pip wheel --find-links packaging/source/wheels --wheel-dir packaging/source/wheels $env:REPO_ZIP_URL

    pushd packaging\source
        New-Item -ItemType directory "pip","python","virtualenv"
        Invoke-RestMethod -Uri http://repository.cloudifysource.org/cloudify/components/win-cli-package-resources/get-pip.py -OutFile pip\get-pip.py
        Invoke-RestMethod -Uri http://repository.cloudifysource.org/cloudify/components/win-cli-package-resources/pip-6.1.1-py2.py3-none-any.whl -OutFile pip\pip-6.1.1-py2.py3-none-any.whl
        Invoke-RestMethod -Uri http://repository.cloudifysource.org/cloudify/components/win-cli-package-resources/setuptools-15.2-py2.py3-none-any.whl -OutFile pip\setuptools-15.2-py2.py3-none-any.whl
        Invoke-RestMethod -Uri http://repository.cloudifysource.org/cloudify/components/win-cli-package-resources/python.msi -OutFile python\python.msi
        Invoke-RestMethod -Uri http://repository.cloudifysource.org/cloudify/components/win-cli-package-resources/virtualenv-15.1.0-py2.py3-none-any.whl -OutFile virtualenv\virtualenv-15.1.0-py2.py3-none-any.whl
    popd
}

function build_win_agent ($VERSION,$PRERELEASE) {
    echo "### Build windows agent ###"
    $env:VERSION = $VERSION
    $env:PRERELEASE = $PRERELEASE
    & "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" packaging/create_install_wizard.iss
}

function s3_uploader ($s3_path) {
    echo "### Upload to S3 ###"
    pushd packaging\output
        $artifact = "cloudify-windows-agent_$env:VERSION-$env:PRERELEASE.exe"
        $artifact_md5 = $(Get-FileHash -Path $artifact -Algorithm MD5).Hash
        "$artifact_md5 $artifact" > "$artifact.md5"

        aws s3 cp .\ $s3_path --acl public-read --recursive
    popd
}


### Main ###

# resolving git branch releated settings
git clone https://github.com/cloudify-cosmo/cloudify-agent.git
cd cloudify-agent\
resolve_current_build_branch_urls
git checkout $env:current_branch

cd packaging\windows
preparation
build_win_agent $VERSION $PRERELEASE

echo "S3 url: $env:AWS_S3_PATH"
s3_uploader $env:AWS_S3_PATH