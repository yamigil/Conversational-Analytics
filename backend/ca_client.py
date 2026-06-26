import os
import logging
from google.cloud import geminidataanalytics
from google.protobuf.json_format import MessageToDict

logger = logging.getLogger("ca-web-app-client")

class ConversationalAnalyticsClient:
    def __init__(self, project_id: str, user_token: str = None, location: str = "global"):
        self.project_id = project_id
        self.user_token = user_token
        self.location = location or "global"

    def _get_location_from_name(self, resource_name: str) -> str:
        """Helper to extract location from a resource path."""
        if not resource_name:
            return "global"
        parts = resource_name.split("/")
        if "locations" in parts:
            idx = parts.index("locations")
            if idx + 1 < len(parts):
                return parts[idx + 1]
        return "global"

    def _get_agent_client(self, location: str = "global"):
        opts = None
        if location and location != "global":
            opts = {"api_endpoint": f"{location}-geminidataanalytics.googleapis.com"}
            
        if self.user_token:
            from google.oauth2.credentials import Credentials
            creds = Credentials(token=self.user_token)
            return geminidataanalytics.DataAgentServiceClient(credentials=creds, client_options=opts)
        else:
            return geminidataanalytics.DataAgentServiceClient(client_options=opts)

    def _get_chat_client(self, location: str = "global"):
        opts = None
        if location and location != "global":
            opts = {"api_endpoint": f"{location}-geminidataanalytics.googleapis.com"}
            
        if self.user_token:
            from google.oauth2.credentials import Credentials
            creds = Credentials(token=self.user_token)
            return geminidataanalytics.DataChatServiceClient(credentials=creds, client_options=opts)
        else:
            return geminidataanalytics.DataChatServiceClient(client_options=opts)

    def list_agents(self):
        """Lists all data agents in the configured location(s). Supports 'all' and comma-separated lists."""
        if self.location.lower() == "all":
            target_locations = ["global", "us"]
        elif "," in self.location:
            target_locations = [l.strip().lower() for l in self.location.split(",") if l.strip()]
        else:
            target_locations = [self.location.lower()]
            
        results = []
        for loc in target_locations:
            parent = f"projects/{self.project_id}/locations/{loc}"
            try:
                agent_client = self._get_agent_client(loc)
                logger.info(f"Listing accessible data agents with parent={parent} using client for {loc}")
                request = geminidataanalytics.ListAccessibleDataAgentsRequest(parent=parent)
                agents = agent_client.list_accessible_data_agents(request=request)
                
                for agent in agents:
                    agent_dict = MessageToDict(agent._pb if hasattr(agent, '_pb') else agent)
                    # Filter out soft-deleted agents
                    if "deleteTime" in agent_dict:
                        continue
                    results.append(agent_dict)
            except Exception as e:
                logger.warning(f"Failed listing agents via list_accessible_data_agents for location {loc}: {e}")
                # Abort immediately on definitive authentication errors to avoid slow sequential timeouts
                if "401" in str(e) or "unauthenticated" in str(e).lower():
                    raise e
                # Skip fallback if it is a clear permission denied (403) or not found
                if "403" in str(e) or "denied" in str(e).lower() or "404" in str(e):
                    continue
                
                try:
                    agent_client = self._get_agent_client(loc)
                    request = geminidataanalytics.ListDataAgentsRequest(parent=parent)
                    agents = agent_client.list_data_agents(request=request)
                    for agent in agents:
                        agent_dict = MessageToDict(agent._pb if hasattr(agent, '_pb') else agent)
                        # Filter out soft-deleted agents
                        if "deleteTime" in agent_dict:
                            continue
                        results.append(agent_dict)
                except Exception as ex:
                    logger.warning(f"Failed fallback list for location {loc}: {ex}")
                
        return results

    def get_agent(self, agent_name: str):
        """Retrieves a single data agent by name from the GCP API."""
        try:
            agent_client = self._get_agent_client("global")
            request = geminidataanalytics.GetDataAgentRequest(name=agent_name)
            agent = agent_client.get_data_agent(request=request)
            return MessageToDict(agent._pb if hasattr(agent, '_pb') else agent)
        except Exception as e:
            logger.error(f"Failed to fetch data agent '{agent_name}' from API: {e}")
            raise e


    def create_conversation(self, agent_name: str):
        """Creates a new conversation reference with a specific agent."""
        # Conversations are always stored in 'global' region to ensure stability and compatibility with all agent locations
        loc = "global"
        parent = f"projects/{self.project_id}/locations/{loc}"
        
        conversation = geminidataanalytics.Conversation()
        conversation.agents = [agent_name]

        request = geminidataanalytics.CreateConversationRequest(
            parent=parent,
            conversation=conversation,
        )
        chat_client = self._get_chat_client(loc)
        convo = chat_client.create_conversation(request=request)
        return MessageToDict(convo._pb if hasattr(convo, '_pb') else convo)

    def list_conversations(self, agent_name: str = None):
        """Lists active conversations, optionally filtering by agent."""
        # Since conversations are always created in 'global' region, we list them from global parent
        loc = "global"
        parent = f"projects/{self.project_id}/locations/{loc}"
        
        request = geminidataanalytics.ListConversationsRequest(
            parent=parent,
            page_size=100,
        )
        chat_client = self._get_chat_client(loc)
        convos = chat_client.list_conversations(request=request)
        
        results = []
        for convo in convos:
            convo_dict = MessageToDict(convo._pb if hasattr(convo, '_pb') else convo)
            # If agent_name is specified, filter by agent matching
            if agent_name:
                if 'agents' in convo_dict and agent_name in convo_dict['agents']:
                    results.append(convo_dict)
            else:
                results.append(convo_dict)
        return results

    def list_messages(self, conversation_name: str):
        """Lists all messages inside a specific conversation."""
        loc = self._get_location_from_name(conversation_name)
        
        request = geminidataanalytics.ListMessagesRequest(parent=conversation_name)
        chat_client = self._get_chat_client(loc)
        msgs = chat_client.list_messages(request=request)
        
        results = []
        for msg in msgs:
            msg_dict = MessageToDict(msg._pb if hasattr(msg, '_pb') else msg)
            if "message" in msg_dict:
                results.append(msg_dict["message"])
            else:
                results.append(msg_dict)
        # Reverse to get chronological order (API lists in descending order of create time)
        return list(reversed(results))

    def chat_stream(self, conversation_name: str, agent_name: str, message_text: str, looker_credentials: dict = None, inline_context: geminidataanalytics.Context = None):
        """Sends a message to the conversation and yields chunks of the response."""
        loc = self._get_location_from_name(conversation_name)
        parent = f"projects/{self.project_id}/locations/{loc}"
        
        user_msg = geminidataanalytics.Message(user_message={"text": message_text})
        
        convo_ref = geminidataanalytics.ConversationReference()
        convo_ref.conversation = conversation_name
        convo_ref.data_agent_context.data_agent = agent_name
        
        # Inject Looker credentials if provided
        if looker_credentials:
            credentials = geminidataanalytics.Credentials()
            credentials.oauth.secret.client_id = looker_credentials.get("client_id")
            credentials.oauth.secret.client_secret = looker_credentials.get("client_secret")
            convo_ref.data_agent_context.credentials = credentials

        request_args = {
            "parent": parent,
            "messages": [user_msg],
            "conversation_reference": convo_ref,
        }
        if inline_context:
            request_args["inline_context"] = inline_context

        request = geminidataanalytics.ChatRequest(**request_args)
        
        # Call the chat endpoint and yield messages
        chat_client = self._get_chat_client(loc)
        responses = chat_client.chat(request=request)
        for resp in responses:
            yield MessageToDict(resp._pb if hasattr(resp, '_pb') else resp)

    def delete_conversation(self, conversation_name: str):
        """Deletes a conversation on the server."""
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        
        loc = self._get_location_from_name(conversation_name)
        
        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        authed_session = AuthorizedSession(credentials)
        
        domain_prefix = "" if loc == "global" else f"{loc}-"
        url = f"https://{domain_prefix}geminidataanalytics.googleapis.com/v1alpha/{conversation_name}"
        response = authed_session.delete(url)
        if response.status_code != 200:
            raise Exception(f"Failed to delete conversation: {response.text}")
        return {"status": "success"}


