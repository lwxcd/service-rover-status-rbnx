# SPDX-License-Identifier: MulanPSL-2.0
"""Resolve read-only ROS endpoints from Atlas with per-role degradation.

Resolution is best-effort: the service must stay ACTIVE and keep serving
whatever sources exist. Roles without a provider fall back to the stack's
deployment-default topic, and explicit ``topic_remap`` entries skip Atlas.
"""

from __future__ import annotations

from .config import CONTRACTS, ROLES


def resolve(config, service, atlas=None):
    """Return ``(topics, sources, channels)`` for the six subscription roles.

    ``atlas`` is injectable for tests. Channels stay open for the lifetime of
    the service and must be closed by the caller on deactivate/shutdown.
    """
    if atlas is None:
        from robonix_api import ATLAS as atlas  # noqa: N813

    topics = dict(config["topics"])
    sources = {role: "default" for role in ROLES}
    channels = []

    for role, topic in config["topic_remap"].items():
        topics[role] = topic
        sources[role] = "config"

    if config["resolve_providers"]:
        for role in ROLES:
            if role in config["topic_remap"]:
                continue
            provider_id = config["provider_ids"].get(role, "")
            try:
                found = atlas.find_capability(
                    contract_id=CONTRACTS[role],
                    transport="ros2",
                    provider_id=provider_id,
                )
            except Exception as exc:  # noqa: BLE001
                sources[role] = f"default (atlas error: {exc})"
                continue
            if not found:
                sources[role] = "default (no provider)"
                continue
            try:
                channel = service.connect_capability(
                    found[0], contract_id=CONTRACTS[role], transport="ros2")
            except Exception as exc:  # noqa: BLE001
                sources[role] = f"default (connect error: {exc})"
                continue
            if not channel.endpoint:
                channel.close()
                sources[role] = "default (empty endpoint)"
                continue
            if channel.endpoint in {topics[r] for r in ROLES if r != role}:
                channel.close()
                sources[role] = "default (duplicate endpoint)"
                continue
            channels.append(channel)
            topics[role] = channel.endpoint
            sources[role] = f"atlas:{found[0].provider_id}"

    return topics, sources, channels
