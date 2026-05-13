# SPDX-FileCopyrightText: 2025 Weibo, Inc.
#
# SPDX-License-Identifier: Apache-2.0

"""
Group-Agent Binding Manager for IM Channels.

This module provides group-level agent (team) binding for IM channel integrations
(DingTalk, Feishu, Telegram, etc.). In group chats, the agent selection is bound
to the group (conversation) rather than individual users. The last user who binds
an agent to the group determines the agent used for the entire group.

This is separate from user-level team selection (team_selection.py) which is used
for private chats.
"""

import json
import logging
from dataclasses import asdict, dataclass
from typing import Optional

from app.core.cache import cache_manager

logger = logging.getLogger(__name__)

# Redis key prefix for group-agent binding
GROUP_AGENT_BINDING_KEY_PREFIX = "channel:group_agent_binding:"
# TTL for group-agent binding (30 days)
GROUP_AGENT_BINDING_TTL = 30 * 24 * 60 * 60


@dataclass
class GroupAgentBinding:
    """Group-agent binding information.

    Attributes:
        team_id: Database ID of the bound team
        team_name: Name of the team (Kind.name)
        team_namespace: Namespace of the team (Kind.namespace)
        display_name: Optional display name from spec
        bound_by_user_id: Wegent user ID who last bound this agent
        bound_by_user_name: Username of the user who last bound this agent
    """

    team_id: int
    team_name: str
    team_namespace: str = "default"
    display_name: Optional[str] = None
    bound_by_user_id: Optional[int] = None
    bound_by_user_name: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GroupAgentBinding":
        """Create from dictionary."""
        return cls(**data)

    def get_full_name(self) -> str:
        """Get full team identifier with namespace."""
        if self.team_namespace != "default":
            return f"{self.team_namespace}/{self.team_name}"
        return self.team_name


class GroupAgentBindingManager:
    """Manager for group-agent binding in IM channels.

    In group chats, the agent (team) selection is bound to the conversation
    (group) itself. When a user switches agents via /agents command in a group,
    the new agent is bound to that group for all members. The last user who
    binds an agent wins.
    """

    def _get_key(self, channel_type: str, conversation_id: str) -> str:
        """Get Redis key for group-agent binding.

        Args:
            channel_type: Channel type (dingtalk, feishu, etc.)
            conversation_id: Channel-specific conversation/group ID

        Returns:
            Redis key string
        """
        return f"{GROUP_AGENT_BINDING_KEY_PREFIX}{channel_type}:{conversation_id}"

    async def get_binding(
        self, channel_type: str, conversation_id: str
    ) -> Optional[GroupAgentBinding]:
        """Get group-agent binding from Redis.

        Args:
            channel_type: Channel type (dingtalk, feishu, etc.)
            conversation_id: Channel-specific conversation/group ID

        Returns:
            GroupAgentBinding if found, None otherwise
        """
        if not conversation_id:
            return None

        key = self._get_key(channel_type, conversation_id)
        data = await cache_manager.get(key)

        if data:
            try:
                if isinstance(data, str):
                    data = json.loads(data)
                return GroupAgentBinding.from_dict(data)
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                logger.warning(
                    f"[GroupAgentBindingManager] Failed to parse binding for "
                    f"{channel_type}:{conversation_id}: {e}"
                )
                return None

        return None

    async def set_binding(
        self,
        channel_type: str,
        conversation_id: str,
        binding: GroupAgentBinding,
    ) -> None:
        """Set group-agent binding in Redis.

        Args:
            channel_type: Channel type (dingtalk, feishu, etc.)
            conversation_id: Channel-specific conversation/group ID
            binding: Group agent binding to save
        """
        if not conversation_id:
            logger.warning(
                f"[GroupAgentBindingManager] Cannot set binding: empty conversation_id"
            )
            return

        key = self._get_key(channel_type, conversation_id)
        try:
            await cache_manager.set(
                key, json.dumps(binding.to_dict()), expire=GROUP_AGENT_BINDING_TTL
            )
            logger.info(
                f"[GroupAgentBindingManager] Saved group-agent binding for "
                f"{channel_type}:{conversation_id}: team={binding.team_name} "
                f"(id={binding.team_id}, bound_by={binding.bound_by_user_name})"
            )
        except Exception as e:
            logger.error(
                f"[GroupAgentBindingManager] Failed to save binding for "
                f"{channel_type}:{conversation_id}: {e}"
            )

    async def clear_binding(self, channel_type: str, conversation_id: str) -> None:
        """Clear group-agent binding (revert to default).

        Args:
            channel_type: Channel type (dingtalk, feishu, etc.)
            conversation_id: Channel-specific conversation/group ID
        """
        if not conversation_id:
            return

        key = self._get_key(channel_type, conversation_id)
        await cache_manager.delete(key)
        logger.info(
            f"[GroupAgentBindingManager] Cleared group-agent binding for "
            f"{channel_type}:{conversation_id}"
        )


# Global instance
group_agent_binding_manager = GroupAgentBindingManager()
