# datadog-oom-journald
Datadog custom check to publish a count of Linux oom-killer actions, for machines with systemd-journald

To use, add `oom.py` to your `checks.d` directory (probably `/etc/dd-agent/checks.d`) and add `oom.yaml` (which needs no further configuration) to your `conf.d` directory (probably `/etc/dd-agent/conf.d`).

You need to make sure that the user that runs the datadog agent can read the system journal. Adding them to the `systemd-journal` group should do the trick: `usermod -aG systemd-journal dd-agent`
