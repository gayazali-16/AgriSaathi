# Deployment

The maintained instructions for this submitted repository are in
[DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md).

That guide covers Google Cloud setup, builds, secrets, the single-container
deployment, its actual HTTPS link, verification, optional OpenWeather and a local
Docker check. Local development setup is in [README.md](../README.md).

This remains a public-account demonstration with SQLite/local uploads. Cloud Run
can lose runtime state on restart/redeployment; no durable hosted database or
production identity provider is claimed. The checked-in reference artifacts are
historical/modelled and do not become field measurements when deployed.
