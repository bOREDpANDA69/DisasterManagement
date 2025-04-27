import os
from dotenv import load_dotenv
import groq
import time
import json

# Load environment variables
load_dotenv()

# Initialize the Groq client
client = groq.Groq(api_key=os.getenv("GROQ_API_KEY"))

class ChatBot:
    def __init__(self, model="llama3-70b-8192"):
        """Initialize the chatbot with a specific model"""
        self.model = model
        self.conversation_history = []
        self.system_prompt = """You are a expert in disaster response. You are handling multiple agents in the disaster response.
                                1: Prioritizing human lives: Always prioritize the safety and well-being of people affected by the disaster.
                                2: Provide immediate aid and rescue to the affected areas.
                                3: Minimize infrastructure damage and loss.
                                4: Contain the disaster and prevent it from spreading.
                                5: Coordinate with other disaster response teams and resources.
                                Provide concise, accurate responses and maintain context of the conversation. Tell the user when getting out of context."""
        
    def add_message(self, role, content):
        """Add a message to the conversation history"""
        self.conversation_history.append({"role": role, "content": content})
    
    def format_messages(self):
        """Format messages for the API call"""
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self.conversation_history)
        return messages
        
    def generate_response(self, user_input):
        """Generate a response based on the conversation history and user input"""
        # Add user message to history
        self.add_message("user", user_input)
        
        # Call the Groq API
        try:
            start_time = time.time()
            
            completion = client.chat.completions.create(
                model=self.model,
                messages=self.format_messages(),
                temperature=0.7,
                max_tokens=1024,
                top_p=1,
                stream=False
            )
            
            end_time = time.time()
            
            # Extract the response
            response = completion.choices[0].message.content
            
            # Add assistant response to history
            self.add_message("assistant", response)
            
            # Calculate metrics
            tokens_used = completion.usage.total_tokens
            response_time = end_time - start_time
            
            return {
                "response": response,
                "tokens_used": tokens_used,
                "response_time": response_time
            }
            
        except Exception as e:
            print(f"Error generating response: {e}")
            return {
                "response": "I'm sorry, I encountered an error. Please try again.",
                "tokens_used": 0,
                "response_time": 0
            }
    
    def display_conversation(self):
        """Display the entire conversation history"""
        for message in self.conversation_history:
            role = message["role"]
            content = message["content"]
            prefix = "You: " if role == "user" else "Bot: "
            print(f"{prefix}{content}")
            print("-" * 50)
    
    def save_conversation(self, filename="conversation_history.json"):
        """Save the conversation history to a file"""
        with open(filename, "w") as f:
            json.dump(self.conversation_history, f, indent=2)
        print(f"Conversation saved to {filename}")
    
    def load_conversation(self, filename="conversation_history.json"):
        """Load a conversation history from a file"""
        try:
            with open(filename, "r") as f:
                self.conversation_history = json.load(f)
            print(f"Conversation loaded from {filename}")
        except FileNotFoundError:
            print(f"File {filename} not found. Starting with an empty conversation.")


def main():
    """Main function to run the chatbot"""
    print("Welcome to the Groq-powered Chatbot!")
    print("Type 'exit' to end the conversation.")
    print("Type 'save' to save the conversation.")
    print("Type 'load' to load a previous conversation.")
    print("Type 'history' to display the conversation history.")
    print("=" * 50)
    
    # Check if API key is set
    if not os.getenv("GROQ_API_KEY"):
        print("ERROR: GROQ_API_KEY environment variable not set.")
        print("Please create a .env file with your Groq API key or set it directly.")
        return
    
    # Create chatbot instance
    chatbot = ChatBot()
    
    # Start conversation loop
    while True:
        user_input = input("You: ")
        
        if user_input.lower() == "exit":
            print("Goodbye!")
            break
        
        elif user_input.lower() == "save":
            chatbot.save_conversation()
            continue
        
        elif user_input.lower() == "load":
            filename = input("Enter filename (default: conversation_history.json): ")
            if not filename:
                filename = "conversation_history.json"
            chatbot.load_conversation(filename)
            continue
        
        elif user_input.lower() == "history":
            chatbot.display_conversation()
            continue
        
        # Generate and display response
        result = chatbot.generate_response(user_input)
        
        print(f"Bot: {result['response']}")
        print(f"[Tokens: {result['tokens_used']}, Response time: {result['response_time']:.2f}s]")
        print("-" * 50)


if __name__ == "__main__":
    main()
