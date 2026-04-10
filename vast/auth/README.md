# VAST Authentication Utilities
This directory contains tools for managing sessions and security tokens for the VAST Data Management System (VMS).

## Tools
### [vast_get_token.py](./vast_get_token.py)
**Version:** 0.1.0  
**Description:** Exchanges legacy username/password credentials for a long-lived REST API Token.

## Configuration
All tools in this directory rely on the `~/.vastconf` file.

### Required `~/.vastconf` Format:
{
    "vms": "var203.selab.vastdata.com",
    "user": "admin",
    "tenant": "us-central",
    "password": "YOUR_PASSWORD"
}

## Usage
To generate a new token and display it to the console:
python3 vast_get_token.py

## Security Note
API Tokens are safer than hardcoding passwords in scripts. Once a token is generated, you can update your environment or automation to use the token exclusively.
