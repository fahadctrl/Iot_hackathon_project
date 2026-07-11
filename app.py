import aws_cdk as cdk
# Import the class exactly as named in the stack file
from iot_hackathon_project.iot_hackathon_project_stack import IotHackathonStack

app = cdk.App()

# Use the class name here
IotHackathonStack(app, "IotHackathonProjectStack")

app.synth()