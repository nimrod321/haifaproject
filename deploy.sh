#!/usr/bin/env bash
# Deploys the current branch to the live Lightsail server.
# Requires the "lightsail" host alias in ~/.ssh/config.
set -e
git push
ssh lightsail "cd ~/haifa_project && git pull --ff-only && sudo systemctl restart haifa && sleep 2 && systemctl is-active --quiet haifa && echo 'Deployed and running.'"
