import argparse
import json
import os
import requests
import socket
import configparser
from tld import get_fld
import psutil

CONFIGURATION_FILE = os.path.expanduser('~/') + '.cloudflare-ddns-'

EXTERNAL_IP_QUERY_API = 'https://api.ipify.org/?format=json'
CLOUDFLARE_ZONE_QUERY_API = 'https://api.cloudflare.com/client/v4/zones'  # GET
CLOUDFLARE_ZONE_DNS_RECORDS_QUERY_API = 'https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records'  # GET
CLOUDFLARE_ZONE_DNS_RECORDS_UPDATE_API = 'https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{dns_record_id}'  # PUT


def load_arguments():
    """
    Arguments to the program.
    :return: An objects with argument name properties
    """
    parser = argparse.ArgumentParser()
    parser.add_argument('--configure', action='store_true',
                        help='Interactively configure the account and domain for the DDNS updates')
    parser.add_argument('--update-now', action='store_true', help='Update DNS records right now')
    parser.add_argument('--config', default='default')
    return parser.parse_args()


def load_configuration():
    """
    Loads the configuration file from disk.
    :return: A dictionary that either has all the keys read from the configuration file,
             or an empty dictionary if there was an error reading the file.
    """
    try:
        # Attempt to parse configuration file
        config = configparser.ConfigParser()
        config.read(CONFIGURATION_FILE)

        # Ensure all fields are present
        if ('domains' in config['Cloudflare DDNS']):
            if (config['Cloudflare DDNS']['auth_type'] == 'token' and 'api_token' in config['Cloudflare DDNS']):
                return config['Cloudflare DDNS']
            elif (config['Cloudflare DDNS']['auth_type'] == 'key' and all(
                    [key in config['Cloudflare DDNS'] for key in ['email', 'api_key']])):
                return config['Cloudflare DDNS']
        else:
            print(
                'Configuration file {config_file} is missing parameters. Run cloudflare-ddns --configure to set the configuration.'.format(
                    config_file=CONFIGURATION_FILE))
            return {}
    except KeyError:
        print('Configuration file {config_file} not found or invalid! Did you run cloudflare-ddns --configure?'.format(
            config_file=CONFIGURATION_FILE))
        return {}


def initialize_configuration():
    """
    Initializes the configuration file via an interactive shell.
    :return: None, but writes the data to CONFIGURATION_FILE
    """
    config = configparser.ConfigParser()
    config['Cloudflare DDNS'] = {}
    print('=============Configuring CloudFlare automatic DDNS update client=============')
    print('You may rerun this at any time with cloudflare-ddns --configure')
    print('Quit and cancel at any time with Ctrl-C')
    print('')
    auth_type = input(
        'Use API token or API key to authenticate?\nSee https://dash.cloudflare.com/profile/api-tokens for more info.\nEnter [T]oken or [K]ey: ')
    if auth_type.lower() == 't' or auth_type.lower() == 'token':
        config['Cloudflare DDNS']['auth_type'] = 'token'
        api_token = input(
            'Enter the API token you created at https://dash.cloudflare.com/profile/api-tokens.\nRequired permissions are READ Account.Access: Organizations, Identity Providers, and Groups; READ Zone.Zone; EDIT Zone.DNS\nExample: XhtcWvLmWBFGRW-YSK52WBghKtfC40rtuysLAETs\nCloudFlare API token: ')
        config['Cloudflare DDNS']['api_token'] = api_token
    elif auth_type.lower() == 'k' or auth_type.lower() == 'key':
        config['Cloudflare DDNS']['auth_type'] = 'key'
        email = input(
            'Enter the email address associated with your CloudFlare account.\nExample: developer@kevinlin.info\nEmail: ')
        print('')
        api_key = input(
            'Enter the API key associated with your CloudFlare account. You can find your API key at https://dash.cloudflare.com/profile/api-tokens\nExample: 7d9dfl2fid74lsg50saa9j2dbqm67zn39v673\nCloudFlare API key: ')
        print('')
        config['Cloudflare DDNS']['email'] = email
        config['Cloudflare DDNS']['api_key'] = api_key
    domains = input(
        'Enter the domains for which you would like to automatically update the DNS records, delimited by a single comma.\nExample: kevinlin.info,cloudflaremanager.com\nComma-delimited domains: ')
    config['Cloudflare DDNS']['domains'] = domains
    prefix = input("Enter the ip prefix \nExample: 10.0.117: ")
    config['Cloudflare DDNS']['prefix'] = prefix
    with open(CONFIGURATION_FILE, 'w') as config_file:
        config.write(config_file)
    print('')
    print('Configuration file written to {config_file} successfully.'.format(config_file=CONFIGURATION_FILE))


def get_external_ip(prefix):
    """
    Get the external IP of the network the script where the script is being executed.
    :return: A string representing the network's external IP address
    """
    # return requests.get(EXTERNAL_IP_QUERY_API, timeout=6).json()['ip']
    interfaces = psutil.net_if_addrs()
    for i, k in interfaces.items():
        for a in k:
            if a.family == socket.AF_INET:
                if prefix in a.address:
                    return a.address


def update_dns_record(auth, zone_id, record, ip_address):
    if record is None or ip_address is None:
        return
    print(
        'Updating the {type} record (ID {dns_record_id}) of (sub)domain {subdomain} (ID {zone_id}) to {ip_address}.'.format(
            type=record['type'], dns_record_id=record['id'], zone_id=zone_id, subdomain=record['name'],
            ip_address=ip_address))
    if record['content'] == ip_address:
        print('DNS record is already up-to-date; taking no action')
        return
    update_resp = requests.put(
        CLOUDFLARE_ZONE_DNS_RECORDS_UPDATE_API.format(zone_id=zone_id, dns_record_id=record['id']),
        headers=dict(list(auth.items()) + [('Content-Type', 'application/json')]),
        data=json.dumps({'type': record['type'], 'name': record['name'], 'content': ip_address}),
        timeout=6,
    )
    if update_resp.json()['success']:
        print('DNS record updated successfully!')
    else:
        print(
            'DNS record failed to update.\nCloudFlare returned the following errors: {errors}.\nCloudFlare returned the following messages: {messages}'.format(
                errors=update_resp.json()['errors'], messages=update_resp.json()['messages']))


def update_dns(subdomain, auth, ipv4_address, ipv6_address):
    """
    Updates the specified domain with the given IP address, given authentication parameters.
    :param domain: String representing domain to update
    :param auth: Dictionary of API authentication credentials
    :param ipv4_address: IPv4 address with which to update the A record
    :param ipv6_address: IPv6 address with which to update the AAAA record
    :return: None
    """
    # Extract the domain
    domain = get_fld(subdomain, fix_protocol=True)

    # Find the zone ID corresponding to the domain
    cur_page = 1
    zone_names_to_ids = {}
    while True:
        zone_resp = requests.get(CLOUDFLARE_ZONE_QUERY_API, headers=auth, timeout=6,
                                 params={'per_page': 50, 'page': cur_page})
        if zone_resp.status_code != 200:
            print(
                'Authentication error: make sure your email and API key are correct. To set new values, run cloudflare-ddns --configure')
            return
        data = zone_resp.json()
        total_pages = data['result_info']['total_pages']
        for zone in data['result']:
            zone_names_to_ids[zone['name']] = zone['id']
        if (cur_page < total_pages):
            cur_page += 1
        else:
            break

    if domain not in zone_names_to_ids:
        print(
            'The domain {domain} doesn\'t appear to be one of your CloudFlare domains. We only found {domain_list}.'.format(
                domain=domain, domain_list=map(str, zone_names_to_ids.keys())))
        return
    zone_id = zone_names_to_ids[domain]

    # Find DNS records
    record_a = None
    record_aaaa = None
    for dns_record in requests.get(
            CLOUDFLARE_ZONE_DNS_RECORDS_QUERY_API.format(zone_id=zone_id),
            headers=auth,
            params={'name': subdomain},
            timeout=6,
    ).json()['result']:
        if dns_record['type'] == 'A':
            record_a = dns_record
        elif dns_record['type'] == 'AAAA':
            record_aaaa = dns_record

    # Update the record as necessary
    update_dns_record(auth, zone_id, record_a, ipv4_address)
    update_dns_record(auth, zone_id, record_aaaa, ipv6_address)


def get_ipv6():
    """
    Based on: https://gist.github.com/corny/7a07f5ac901844bd20c9
    :return: A string representing one of the network's IPv6 addresses
    """
    interfaces = psutil.net_if_addrs()
    for i, k in interfaces.items():
        for a in k:
            if a.family == socket.AF_INET6:
                return a.address
    return None


def main():
    """
    Main program: either make the configuration file or update the DNS
    """
    global CONFIGURATION_FILE
    args = load_arguments()
    CONFIGURATION_FILE += args.config
    if args.configure:
        initialize_configuration()
    elif args.update_now:
        config = load_configuration()
        if not config:
            print(
                'There was a problem with the configuration file {config_file}! Try running cloudflare-ddns --configure'.format(
                    config_file=CONFIGURATION_FILE))
            return
        if config['auth_type'] == 'token':
            auth = {'Authorization': 'Bearer {token}'.format(token=config['api_token'])}
        elif config['auth_type'] == 'key':
            auth = {'X-Auth-Email': config['email'], 'X-Auth-Key': config['api_key']}
        external_ip = get_external_ip(config['prefix'])
        ipv6 = get_ipv6()
        for domain in config['domains'].split(','):
            update_dns(domain, auth, external_ip, ipv6)
    else:
        print('No arguments passed; exiting.')
        print('Try cloudflare-ddns --help.')


if __name__ == '__main__':
    main()
