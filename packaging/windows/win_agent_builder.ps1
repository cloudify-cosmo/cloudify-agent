param($VERSION,$PRERELEASE)

function preparation () {
    echo "### preparation ###"
    pip install wheel
    pip wheel --wheel-dir packaging/source/wheels --requirement "https://raw.githubusercontent.com/cloudify-cosmo/cloudify-agent/master/dev-requirements.txt"
    pip wheel --find-links packaging/source/wheels --wheel-dir packaging/source/wheels "https://github.com/cloudify-cosmo/cloudify-agent/archive/master.zip"

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
    echo "### build windows agent... ###"
    $env:VERSION = $VERSION
    $env:PRERELEASE = $PRERELEASE
    & "C:\Program Files (x86)\Inno Setup 5\ISCC.exe" packaging/create_install_wizard.iss
}

function s3_uploader ($s3_path) {
    echo "### Upload to S3... ###"
    pushd packaging\output
        $artifact = "cloudify-windows-agent_$env:VERSION-$env:PRERELEASE.exe"
        $artifact_md5 = $(Get-FileHash -Path $artifact -Algorithm MD5).Hash
        "$artifact_md5 $artifact" > "$artifact.md5"

        aws s3 cp .\ $s3_path --acl public-read --recursive
    popd
}


### Main ###

git clone https://github.com/cloudify-cosmo/cloudify-agent.git
cd cloudify-agent\packaging\windows

preparation
build_win_agent $VERSION $PRERELEASE
s3_uploader "s3://cloudify-release-eu/cloudify/$env:VERSION/$env:PRERELEASE-build/"