import os
import boto3
from langchain.prompts import PromptTemplate 
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain.llms.bedrock import Bedrock
import chainlit as cl
from chainlit.input_widget import Select, Slider
from prompt_template import get_template

AWS_REGION = os.environ["AWS_REGION"]

@cl.on_chat_start
async def main():
    bedrock = boto3.client("bedrock", region_name=AWS_REGION)
    
    response = bedrock.list_foundation_models(
        byOutputModality="TEXT"
    )
    
    model_ids = []
    for item in response["modelSummaries"]:
        model_ids.append(item['modelId'])
    
    settings = await cl.ChatSettings(
        [
            Select(
                id="Model",
                label="Amazon Bedrock - Model",
                values=model_ids,
                initial_index=model_ids.index("anthropic.claude-v2"),
            ),
            Slider(
                id="Temperature",
                label="Temperature",
                initial=0.3,
                min=0,
                max=1,
                step=0.1,
            ),
            Slider(
                id="MAX_TOKEN_SIZE",
                label="Max Token Size",
                initial=1024,
                min=256,
                max=4096,
                step=256,
            ),
        ]
    ).send()
    await setup_agent(settings)

@cl.on_settings_update
async def setup_agent(settings):

    bedrock_model_id = settings["Model"]
    
    llm = Bedrock(
        region_name = AWS_REGION,
        model_id = settings["Model"],
        model_kwargs = {"temperature": settings["Temperature"]},
        streaming = True, #Streaming must be set to True for async operations.
    )

    provider = bedrock_model_id.split(".")[0]
    
    human_prefix="Human"
    ai_prefix="AI"

    MAX_TOKEN_SIZE = int(settings["MAX_TOKEN_SIZE"])
    
    # Model specific adjustments
    if provider == "anthropic":
        llm.model_kwargs["max_tokens_to_sample"] = MAX_TOKEN_SIZE
        human_prefix="H"
        ai_prefix="A"
    elif provider == "ai21":
        llm.model_kwargs["maxTokens"] = MAX_TOKEN_SIZE
    elif provider == "cohere":
        llm.model_kwargs["max_tokens"] = MAX_TOKEN_SIZE    
    elif provider == "amazon":
        llm.model_kwargs["maxTokenCount"] = MAX_TOKEN_SIZE
    else:
        print(f"Unsupported Provider: {provider}")

    prompt = PromptTemplate(
        template=get_template(provider),
        input_variables=["history", "input"],
    )
    
    conversation = ConversationChain(
        prompt=prompt, 
        llm=llm, 
        memory=ConversationBufferMemory(
            human_prefix=human_prefix,
            ai_prefix=ai_prefix
        ),
        verbose=True,
    )
    # Set ConversationChain to the user session
    cl.user_session.set("llm_chain", conversation)

@cl.on_message
async def main(message: cl.Message):
    # Get ConversationChain from the user session
    conversation = cl.user_session.get("llm_chain") 

    res = await conversation.ainvoke(
        message.content, 
        callbacks=[cl.AsyncLangchainCallbackHandler()],
    )
    
    await cl.Message(content=res["response"]).send()
