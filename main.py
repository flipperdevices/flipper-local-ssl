#!/usr/bin/env python3.11

import re
import json
import logging
import subprocess
from scp import SCPClient
from paramiko import SSHClient
from paramiko import AutoAddPolicy as ParamikoAutoAddPolicy


class FlipperLocalSSL:
    def __init__(self):
        self._configure_logs()
        self._configure_ssh()
        self.config = []
        self.not_need_to_renew_re = re.compile(r"Certificate not yet due for renewal")
        self._config_parse()

    def _configure_logs(self):
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)

    def _configure_ssh(self):
        self.ssh_client = SSHClient()
        self.ssh_client.set_missing_host_key_policy(ParamikoAutoAddPolicy())

    def _config_parse(self):
        with open("config.json") as json_file:
            self.config = json.load(json_file)

    def make_ssl_cert(self, hostname: str) -> bool:
        logging.info(f"Issuing certificate for {hostname}")
        cert_bot_args = [
            "certbot",
            "certonly",
            "--dns-cloudflare",
            "--dns-cloudflare-credentials",
            "cloudflare.ini",
            "-m",
            self.config["system_email"],
            "--agree-tos",
            "--no-eff-email",
            "-n",
            "-d",
            hostname,
        ]
        res = subprocess.run(
            cert_bot_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout = res.stdout.decode("utf-8")
        stderr = res.stderr.decode("utf-8")
        not_need_to_renew = bool(self.not_need_to_renew_re.match(stdout))
        if res.returncode != 0:
            logging.error(
                f"Failed to issue certificate for {hostname} with code: {res.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
            )
            return False
        elif not_need_to_renew:
            logging.info(f"Certificate for {hostname} is not yet due for renewal")
            return False
        return True

    def copy_cert_on_host(self, host: list) -> bool:
        hostname = host["hostname"]
        logging.info(f"Copying ssl certs to {hostname} via scp")
        port = host["ssh_port"]
        user = host["ssh_user"]
        keyfile = self.config["system_ssh_keyfile"]
        cert_dir = f"/etc/letsencrypt/live/{hostname}"
        self.ssh_client.connect(hostname=hostname, username=user, key_filename=keyfile)
        scp_client = SCPClient(self.ssh_client.get_transport())
        scp_client.put(cert_dir + "/fullchain.pem", f"{hostname}-fullchain.pem")
        scp_client.put(cert_dir + "/privkey.pem", f"{hostname}-privkey.pem")
        scp_client.close()
        self.ssh_client.close()
        logging.info(f"Ssl certs successfully transfered to {hostname}")
        return True

    def exec_post_commands_on_host(self, host: list):
        hostname = host["hostname"]
        logging.info(f"Executing post upload commands on {hostname}")
        port = host["ssh_port"]
        user = host["ssh_user"]
        keyfile = self.config["system_ssh_keyfile"]
        commands = host["post_commands"]
        self.ssh_client.connect(hostname=hostname, username=user, key_filename=keyfile)
        for command in commands:
            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                print(f"{stdin}, {stdout}, {stderr}")

        self.ssh_client.close()
        logging.info(f"Post upload commands are successfully executed on {hostname}")

    def process_host(self, host: list):
        if self.make_ssl_cert(host["hostname"]):
            return
        if not self.copy_cert_on_host(host):
            return
        self.exec_post_commands_on_host(host)

    def main(self):
        [self.process_host(host) for host in self.config["hosts"]]


if __name__ == "__main__":
    ssl_app = FlipperLocalSSL()
    ssl_app.main()
