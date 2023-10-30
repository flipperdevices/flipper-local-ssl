#!/usr/bin/env python3

import re
import json
import time
import logging
import subprocess
from scp import SCPClient
from pygelf import GelfHttpsHandler
from socket import gethostname
from paramiko import SSHClient
from paramiko import AutoAddPolicy as ParamikoAutoAddPolicy


class FlipperLocalSSL:
    def __init__(self):
        self.config = []
        self._config_parse()
        self._configure_logs()
        self._configure_ssh()
        self.not_need_to_renew_re = re.compile(r"Certificate not yet due for renewal")

    def _configure_logs(self):
        self.logger = logging.getLogger()
        self.logger.setLevel(logging.INFO)
        if not self.config.get("gelf"):
            return
        auth_host = self.config["gelf"]["host"]
        auth_port = self.config["gelf"]["port"]
        auth_user = self.config["gelf"]["username"]
        auth_pass = self.config["gelf"]["password"]
        handler = GelfHttpsHandler(
                host=auth_host,
                port=auth_port,
                username=auth_user,
                password=auth_pass,
                _app="flipper-local-ssl",
            )
        self.logger.addHandler(handler)

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
            self.config["system"]["email"],
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
        keyfile = self.config["system"]["ssh_keyfile"]
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
        keyfile = self.config["system"]["ssh_keyfile"]
        commands = host["post_commands"]
        self.ssh_client.connect(hostname=hostname, username=user, key_filename=keyfile)
        for command in commands:
            stdin, stdout, stderr = self.ssh_client.exec_command(command)
            exit_status = stdout.channel.recv_exit_status()
            if exit_status != 0:
                logging.error(
                    f"Failed to execute command '{command}' for {hostname} with code: {exit_status}\nstdout:\n{stdout}\nstderr:\n{stderr}"
                )

        self.ssh_client.close()
        logging.info(f"Post upload commands are successfully executed on {hostname}")

    def process_host(self, host: list):
        if not self.make_ssl_cert(host["hostname"]):
            return
        if not self.copy_cert_on_host(host):
            return
        self.exec_post_commands_on_host(host)

    def main(self):
        sleep_timeout_seconds = self.config["system"]["renew_delay_seconds"]
        while True:
            [self.process_host(host) for host in self.config["hosts"]]
            logging.info(f"Sleeping for {sleep_timeout_seconds} seconds..")
            time.sleep(sleep_timeout_seconds)


if __name__ == "__main__":
    try:
        ssl_app = FlipperLocalSSL()
        ssl_app.main()
    except Exception as e:
        logging.exception(e)
