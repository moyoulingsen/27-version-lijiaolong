# Sentry v1

- `final.pt`: published PPO-LSTM checkpoint.
- `validation.json`: CPU reference-environment validation result.
- `training_metadata.json`: complete environment, network, PPO and training configuration.
- Replays: `../../replays/sentry_v1/`.

This policy is deployed with stochastic action sampling. Pure argmax evaluation
is retained only as a diagnostic mode.

