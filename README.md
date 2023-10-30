# Flipper Let's Encrypt deployer for local hosts

## About
This tool may be useful for deploying Let's Encrypt SSL certificates to private network. It use the certbot with the [certbot-dns-cloudflare](https://github.com/certbot/certbot/tree/master/certbot-dns-cloudflare) plugin. New certificate will be transfered to the specified host after issuing or renewing. You can add post-transfer commands to each host.

## Files requirements
1. cloudflare.ini
2. config.json
3. ssh keys

## cloudflare.ini example
```
dns_cloudflare_api_token = MY_SECRET_TOKEN
```

## config.json example
```json
{
  "system": {
    "email": "email@example.com",
    "ssh_keyfile": ".ssh/flipper-local-ssl",
    "renew_delay_seconds": 86400
  },
  "gelf": {
      "host": "gelf.example.com",
      "port": 1234,
      "username": "user",
      "password": "pass"
  },
  "hosts": [
    {
      "hostname": "gw.example.com",
      "ssh_port": "1234",
      "ssh_user": "user",
      "post_commands": [
          "/certificate/remove gw.example.com-fullchain.pem_0",
          "/certificate/import file-name=gw.example.com-fullchain.pem passphrase=\"\"",
          "/certificate/import file-name=gw.example.com-privkey.pem passphrase=\"\"",
          "/ip/service/set www-ssl certificate=gw.example.com.pem_0"
      ]
    },
    {
      "hostname": "proxmox.example.com",
      "ssh_port": "2222",
      "ssh_user": "user",
      "post_commands": [
          "sudo mv proxmox.example.com-fullchain.pem /etc/pve/local/pveproxy-ssl.pem",
          "sudo mv proxmox.example.com-privkey.pem /etc/pve/local/pveproxy-ssl.key",
          "sudo systemctl restart pveproxy"
      ]
    }
  ]
}
```

## Deploying SSH keys
```bash
ssh-keygen -f .ssh/flipper-local-ssl
ssh-copy-id -i .ssh/flipper-local-ssl.pub user@host
```
