

# Using Amazon States Language to define Step Functions workflows
<a name="concepts-amazon-states-language"></a>

The Amazon States Language is a JSON-based, structured language used to define your state machine, a collection of [states](workflow-states.md), that can do work (`Task` states), determine which states to transition to next (`Choice` states), stop an execution with an error (`Fail` states), and so on. 

For more information, see the [Amazon States Language Specification](https://states-language.net/spec.html) and [Statelint](https://github.com/awslabs/statelint), a tool that validates Amazon States Language code.

To create a state machine on the [Step Functions console](https://console.aws.amazon.com/states/home?region=us-east-1#/) using Amazon States Language, see [Getting Started](getting-started.md).

**Note**  
If you define your state machines outside the Step Functions' console, such as in an editor of your choice, you must save your state machine definitions with the extension *.asl.json*.

## Example Amazon States Language Specification (JSONata)
<a name="example-amazon-states-language-specification"></a>

```
{
  "Comment": "An example of the Amazon States Language using a choice state.",
  "QueryLanguage": "JSONata",
  "StartAt": "FirstState",
  "States": {
    "FirstState": {
      "Type": "Task",
      "Assign": {
        "foo" : "{% $states.input.foo_input %}" 
        },
      "Resource": "arn:aws:lambda:{{region}}:123456789012:function:{{FUNCTION_NAME}}",
      "Next": "ChoiceState"
    },
    "ChoiceState": {
      "Type": "Choice",
      "Default": "DefaultState",
      "Choices": [
        {
          "Next": "FirstMatchState",
          "Condition": "{% $foo = 1 %}"
        },
        {
          "Next": "SecondMatchState",
          "Condition": "{% $foo = 2 %}"
        }
      ]
    },
    "FirstMatchState": {
      "Type" : "Task",
      "Resource": "arn:aws:lambda:{{region}}:123456789012:function:{{OnFirstMatch}}",
      "Next": "NextState"
    },

    "SecondMatchState": {
      "Type" : "Task",
      "Resource": "arn:aws:lambda:{{region}}:123456789012:function:{{OnSecondMatch}}",
      "Next": "NextState"
    },

    "DefaultState": {
      "Type": "Fail",
      "Error": "DefaultStateError",
      "Cause": "No Matches!"
    },

    "NextState": {
      "Type": "Task",
      "Resource": "arn:aws:lambda:{{region}}:123456789012:function:{{FUNCTION_NAME}}",
      "End": true
    }
  }
}
```