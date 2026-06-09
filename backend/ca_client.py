import os
from google.cloud import geminidataanalytics
from google.protobuf.json_format import MessageToDict

class ConversationalAnalyticsClient:
    def __init__(self, project_id: str, user_token: str = None):
        self.project_id = project_id
        self.location = "global"
        self.parent = f"projects/{self.project_id}/locations/{self.location}"
        
        # Initialize Google Cloud clients
        if user_token:
            from google.oauth2.credentials import Credentials
            creds = Credentials(token=user_token)
            self.agent_client = geminidataanalytics.DataAgentServiceClient(credentials=creds)
            self.chat_client = geminidataanalytics.DataChatServiceClient(credentials=creds)
        else:
            self.agent_client = geminidataanalytics.DataAgentServiceClient()
            self.chat_client = geminidataanalytics.DataChatServiceClient()

    def list_agents(self):
        """Lists all data agents in the project location."""
        request = geminidataanalytics.ListDataAgentsRequest(parent=self.parent)
        agents = self.agent_client.list_data_agents(request=request)
        
        results = []
        for agent in agents:
            # Convert the proto-plus/protobuf object to a dictionary
            agent_dict = MessageToDict(agent._pb if hasattr(agent, '_pb') else agent)
            results.append(agent_dict)
        return results

    def create_conversation(self, agent_name: str):
        """Creates a new conversation reference with a specific agent."""
        conversation = geminidataanalytics.Conversation()
        conversation.agents = [agent_name]

        request = geminidataanalytics.CreateConversationRequest(
            parent=self.parent,
            conversation=conversation,
        )
        convo = self.chat_client.create_conversation(request=request)
        return MessageToDict(convo._pb if hasattr(convo, '_pb') else convo)

    def list_conversations(self, agent_name: str = None):
        """Lists active conversations, optionally filtering by agent."""
        request = geminidataanalytics.ListConversationsRequest(
            parent=self.parent,
            page_size=100,
        )
        convos = self.chat_client.list_conversations(request=request)
        
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
        request = geminidataanalytics.ListMessagesRequest(parent=conversation_name)
        msgs = self.chat_client.list_messages(request=request)
        
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
            "parent": self.parent,
            "messages": [user_msg],
            "conversation_reference": convo_ref,
        }
        if inline_context:
            request_args["inline_context"] = inline_context

        request = geminidataanalytics.ChatRequest(**request_args)
        
        # Call the chat endpoint and yield messages
        responses = self.chat_client.chat(request=request)
        for resp in responses:
            yield MessageToDict(resp._pb if hasattr(resp, '_pb') else resp)

    def delete_conversation(self, conversation_name: str):
        """Deletes a conversation on the server."""
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        
        credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
        authed_session = AuthorizedSession(credentials)
        
        url = f"https://geminidataanalytics.googleapis.com/v1alpha/{conversation_name}"
        response = authed_session.delete(url)
        if response.status_code != 200:
            raise Exception(f"Failed to delete conversation: {response.text}")
        return {"status": "success"}

