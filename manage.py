"""Local operator commands; passwords are entered privately, never as arguments."""
import argparse
from getpass import getpass
import os
from transport import Transport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['create-admin'])
    parser.parse_args()
    email = input('Administrator email: ').strip()
    name = input('Administrator name: ').strip()
    password = getpass('Password (at least 10 characters): ')
    if password != getpass('Confirm password: '):
        parser.exit(1, 'Passwords do not match. No account created.\n')
    try:
        service = Transport(os.getenv('TRANSPORT_DB', 'data/transport.db'))
        service.register(name, email, password, role='admin')
    except ValueError as exc:
        parser.exit(1, str(exc) + '\n')
    print('Administrator created. Sign in through the app. Existing accounts were not changed.')


if __name__ == '__main__':
    main()
