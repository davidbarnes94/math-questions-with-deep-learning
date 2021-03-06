import torch
import torch.autograd as autograd
import torch.nn as nn
import torch.optim as optim
import re
import numpy as np
import torch.nn.functional as F
import matplotlib.pyplot as plt

use_cuda = torch.cuda.is_available()
HIDDEN_DIM = 256
MAX_LENGTH = 25 #maximum length of a question

'''
An RNN processes the question. Based on the structure of the dataset, there is a certain number of multiple choice responses for a question.
If there are 4 choices, there'll be 4 answer RNNs in the model. Each choice is processed by a separate answer RNN. The initial hidden state of each answer RNN
is the final hidden state of the question RNN. The method for predicting the correct answer is explained in the function is_accurate()
'''

#Training data with questions, multiple choice answers and the index of correct answer
trainingData = [('Add 3 and 5', [8, 2.3, 9, 14], 0), ('Multiply 9 and 2', [2, 9, 18, 1], 2), ('Divide 9 by 3', [9, 3, 20.3, 6], 1),
                ('John had 3 mangoes then Mary gave him 4 more. How much does he have now?', ["John now has 3 mangoes", "John now has 7 mangoes", "John now has 3 mangoes", "John now has 94 mangoes"], 1),
                ('Sum 50 and 5', [0, 10, 505, 55], 3), ('Adam went to the store with 10 dollars then bought an apple for 6 dollars. How much does he know have?', ["He is left with 4 dollars", "He is left with 100 dollars", "He is left with 6 dollars", "He is left with 12 dollars"], 0), ('Subtract 16 from 30', [-14, 14, 46, 480], 1),
                ('Multiply 2 and 30', [32, 28, 30, 60], 3), ('Add 25 and 39', [64, -14, 6, 45], 0)]

# ('5 + 4 + 25', [3, 20, 34, 5], 2) was removed from the training set due to difficulties in converting it to the required form

testData = [('If Alex had 50 dollars in his account before he deposited 30 dollars. How much does he now have?', ['He now has a total of 80 dollars', 'His account has 30 dollars', 'His account balance is currently 5 dollars', '530 dollars'], 0),
            ('Add 9 and 3', [12, 60, 27, -9.9], 0), ('Subtract 20 from 64', [19.66, 34, 'The result is 15', 9.55], 1), ('Divide 360 by 4', ['It is 90', 5.9, 16, 364], 0), ('Multiply 12 and 3', [12.3, 3.12, 2.3, 36], 3),
            ('What is 2 by 2 by 2?', ['The result is 6', 'The result is 4', 'The result is 8', 'The result is 222'], 2)]

NUM_ANSWERS = len(trainingData[0][1])
loss_function = nn.NLLLoss()


def is_number(s):
    '''

    :param s: variable to be tested
    :return: True if 's' is a number
    '''
    try:
        float(s)
        return True
    except:
        return False

def createQuestionDictionary(data):
    """

    :param data: a list of problems
    :return: a dictionary of all the words and numbers in the questions
    """

    word_to_ix = {}
    for question, answers, ans_index in data:
        words = re.findall(r"[\w']+", question)
        for word in words:
            if word not in word_to_ix:
                word_to_ix[word.lower()] = len(word_to_ix)
    return word_to_ix

def createAnswerDictionary(data):
    """

    :param data: a list of problems
    :return: a dictionary of all the words and numbers in the answers
    """

    word_to_ix = {}
    for question, answers, ans_index in data:
        for choice in answers:
            if is_number(choice) and choice not in word_to_ix:
                word_to_ix[float(choice)] = len(word_to_ix)
            elif isinstance(choice, str):
                words = re.findall(r"[\w']+", choice)
                for word in words:
                    if word not in word_to_ix:
                        word_to_ix[word.lower()] = len(word_to_ix)
    return word_to_ix
train_question_word_to_ix = createQuestionDictionary(trainingData)
test_question_word_to_ix = createQuestionDictionary(testData)
#currently, the '?' isn't being considered
#should numbers be converted from string to integer?

train_answer_word_to_ix = createAnswerDictionary(trainingData)
test_answer_word_to_ix = createAnswerDictionary(testData)

def prepare_data(seq, to_ix):
    """

        :param seq: the list of words in a sentence
        :param to_ix: word_to_ix
        :return: tensor of all the indices of the words
        """
    if is_number(seq):
        idxs = [to_ix[seq]]
    else:
        idxs = [to_ix[re.sub(r'[^\w\s]','', w).lower()] for w in seq]
    tensor = torch.LongTensor(idxs)
    return autograd.Variable(tensor)

def process_question(question, question_model, is_training):
    '''

    :param question: raw string form of the question
    :param question_model: instance of QuestionRNN
    :return: question_outputs: tensor of the final output for each word in the question
    :return: question_hidden: the last hidden state
    '''

    # initialize hidden state of first RNN
    question_hidden = question_model.initHidden()

    question_outputs = autograd.Variable(
        torch.zeros(MAX_LENGTH, question_model.hidden_size))  # store the final output for each word
    question_outputs = question_outputs.cuda() if use_cuda else question_outputs

    if is_training:
        question_in = prepare_data(question.split(), train_question_word_to_ix)
    else:
        question_in = prepare_data(question.split(), test_question_word_to_ix)

    #enter one word at a time into the model to obtain hidden and output states
    for word_index in range(len(question_in)):
        question_output, question_hidden = question_model(question_in[word_index], question_hidden)
        question_outputs[word_index] = question_output[0][0]

    return question_outputs, question_hidden


def plot_gradient(gradient_norms, num_time_steps, model_name):
    '''

    :param gradient_norms: list of the norm of the gradient for each time step
    :param num_time_steps: total time steps
    :param model_name: name of RNN
    :return:
    '''
    norms = np.array(gradient_norms)
    time_steps = np.arange(num_time_steps)
    plt.title(model_name)
    plt.plot(time_steps, norms)
    plt.show()


class QuestionRNN(nn.Module):
    def __init__(self, input_size, hidden_size, n_layers=1):
        super(QuestionRNN, self).__init__()
        self.n_layers = n_layers #number of hidden layers in the LSTM
        self.hidden_size = hidden_size #the dimension of a hidden vector

        self.embedding = nn.Embedding(input_size, hidden_size) #to create an embedding for each word
        self.gru = nn.GRU(hidden_size, hidden_size) #the hidden layer

    def forward(self, input, hidden):
        #the input is an element LongTensor of the corresponding to a word in the input sequence
        embedded = self.embedding(input).view(1, 1, -1) #reshape 1x1xhidden_size tensor
        output = embedded
        for i in range(self.n_layers):
            output, hidden = self.gru(output, hidden)
        return output, hidden

    def initHidden(self):
        result = autograd.Variable(torch.zeros(1, 1, self.hidden_size))
        if use_cuda:
            return result.cuda()
        else:
            return result

class AnswerRNN(nn.Module):
        def __init__(self, input_size, hidden_size, n_layers=1):
            super(AnswerRNN, self).__init__()
            self.n_layers = n_layers  # number of hidden layers in the LSTM
            self.hidden_size = hidden_size  # the dimension of a hidden vector
            self.output2tag = nn.Linear(HIDDEN_DIM, 2)
            self.softmax = nn.LogSoftmax()
            self.embedding = nn.Embedding(input_size, hidden_size)  # to create an embedding for each word
            self.gru = nn.GRU(hidden_size, hidden_size)  # the hidden layer


        def forward(self, input, hidden):
            # the input is an element LongTensor of the corresponding to a word in the input sequence
            embedded = self.embedding(input).view(1, 1, -1)  # reshape 1x1xhidden_size tensor
            output = embedded
            for i in range(self.n_layers):
                output = F.relu(output)
                output, hidden = self.gru(output, hidden)
            softmax_layer = self.softmax(self.output2tag(output[0]))
            return softmax_layer, hidden


        def initHidden(self):
            result = autograd.Variable(torch.zeros(1, 1, self.hidden_size))
            if use_cuda:
                return result.cuda()
            else:
                return result

def process_answer(answer, answer_model, question_final_hidden, is_training):
    '''

    :param answer: raw form of an answer choice for a question
    :param answer_model: instance of AnswerRNN
    :param question_final_hidden: last hidden state from the question RNN
    :param is_training: True if training data is used
    :return: softmax over 0 and 1 from the final output of the RNN
    '''

    if is_number(answer) and is_training:
        answer_in = prepare_data(answer, train_answer_word_to_ix)
    elif is_number(answer) and not is_training:
        answer_in = prepare_data(answer, test_answer_word_to_ix)
    elif not is_number(answer) and not is_training:
        answer_in = prepare_data(answer.split(), test_answer_word_to_ix)
    else:
        answer_in = prepare_data(answer.split(), train_answer_word_to_ix)

    answer_hidden = question_final_hidden #last hidden state from the question becomes the initial hidden state of the answer model

    #enter one word at a time into the model to obtain hidden and output states
    for word_index in range(len(answer_in)):
        softmax_layer, answer_hidden = answer_model(answer_in[word_index], answer_hidden)

    return softmax_layer


def is_accurate(predicted_tags, ans_index):
    '''

    :param predicted_tags: Variable with each row being the log softmax over 0 and 1 for belief in the correctness of that answer
    :param ans_index: list index of the correct answer
    :return: True if model predicted the correct answer and vice-versa. List index of the predicted answer.

    method for predicting the correct answer:
    - an answer will be considered for possibly being the correct response if its log softmax value for 1 is larger than that of 0
    - from the list of possible answers, the one with the highest log softmax value for 1 will be chosen
    - otherwise, no answer is chosen
    '''

    predicted_tags = predicted_tags.data.numpy()
    max_ones = [-100]*len(predicted_tags)
    for i, tag_scores in enumerate(predicted_tags):
        if tag_scores[1] > tag_scores[0]:
            max_ones[i] = tag_scores[1]

    max_one = max_ones.index(max(max_ones))
    if max_one == ans_index:
        return True, max_one
    else:
        return False, max_one

def create_models():
    '''
    create an RNN to process the question and each of the n answers
    :return: questionModel: an instance of QuestionRNN
    :return: question_optimizer: updates parameters during training
    :return: answer_models: list of all the instances of AnswerRNN
    :return: answer_optimizers: list of the optimizers for each answer_model
    '''
    questionModel = QuestionRNN(len(train_question_word_to_ix), HIDDEN_DIM)
    answer_models = []
    for i in range(NUM_ANSWERS):
        answer_models.append(AnswerRNN(len(train_answer_word_to_ix), HIDDEN_DIM))

    question_optimizer = optim.SGD(questionModel.parameters(), lr=0.1)
    answer_optimizers = []
    for i in range(NUM_ANSWERS):
        answer_optimizers.append(optim.SGD(answer_models[i].parameters(), lr=0.1))

    return questionModel, question_optimizer, answer_models, answer_optimizers


def train_one_AnswerRNN(answer_model, answer_optimizer, question_model, question_optimizer, question, choice, true_tag):
    '''

    :param answer_model: instance of AnswerRNN
    :param answer_optimizer: updates the parameters of answer_model during training
    :param question_model: instance of QuestionRNN
    :param question_optimizer: updates the parameters of question_model during training
    :param question: raw string form of question
    :param choice: one of the multiple choice responses
    :param true_tag: 1 if choice is correct answer, 0 otherwise
    :return:
    '''
    # set all gradients to zero
    question_model.zero_grad()
    answer_model.zero_grad()
    # feed the question through the question RNN
    question_outputs, last_hidden = process_question(question, question_model, True)


    # RNN outputs a softmax over 0 and 1
    # 0 - it is not the correct answer
    # 1 - it is the correct answer
    predicted_tags = process_answer(choice, answer_model, last_hidden, True)

    loss = loss_function(predicted_tags, autograd.Variable(torch.LongTensor([true_tag])))
    loss.backward()

    question_optimizer.step()
    answer_optimizer.step()

    return question_model, answer_model


def train(training_data, n_epochs=500):
    '''
    :param training_data: list of 3 element tuples. tuple example: (question, [choice1, choice2,..], index of correct choice)
    :param n_epochs: number of epochs
    :return: question_model: trained question RNN
    :return: answer_models: trained answer RNNs
    '''

    question_model, question_optimizer, answer_models, answer_optimizers = create_models()
    print("Training model for %d epochs." % n_epochs)

    for j in range(NUM_ANSWERS):
        gradient_norms = []
        gradient_norms_question = []
        params = list(answer_models[j].parameters())
        params_question = list(question_model.parameters())
        for _ in range(n_epochs):
            for question, choices, correct_choice_index in training_data:
                true_tag = 1 if correct_choice_index == j else 0
                question_model, answer_models[j] = train_one_AnswerRNN(answer_models[j], answer_optimizers[j],
                                                                       question_model, question_optimizer, question, choices[j], true_tag)
                gradient_norms.append(params[0].grad.data.norm(2))
                gradient_norms_question.append(params_question[0].grad.data.norm(2))

        model_name = 'answer model ' + str(j)
        #plot_gradient(gradient_norms, len(trainingData)*n_epochs, model_name)
    #plot_gradient(gradient_norms_question, len(trainingData)*n_epochs, 'question_model')


    return question_model, answer_models


def test(question_model, answer_models, data, is_training=False):
    '''

    :param question_model: trained RNN for processing the question
    :param answer_models: trained answer RNN's for processing the answers
    :param data: data for testing the model
    :param is_training: True if the training data is used
    :return:
    '''
    if is_training:
        print("\nTesting model on training set.")
    else:
        print("\nTesting model on test set.")

    sumAccuracy = 0
    predicted_tags = autograd.Variable(torch.zeros(NUM_ANSWERS, 2))
    for question, answers, ans_index in data:
        question_in, last_hidden = process_question(question, question_model, is_training)
        for i, answer in enumerate(answers):
            predicted_tags[i] = process_answer(answer, answer_models[i], last_hidden, is_training)

        prediction_accuracy, predicted_index = is_accurate(predicted_tags, ans_index)
        sumAccuracy += int(prediction_accuracy == True)
        try:
            print("question: {0}, correct answer: {1}, predicted_answer: {2}".format(question, answers[ans_index], answers[predicted_index]))
        except:
            print("question: {0}, correct answer: {1}, Model doesn't think any of the answers is correct".format(question, answers[ans_index]))


    return "The model correctly predicted {0} out of {1} questions".format(sumAccuracy, len(data))


##FUNCTION TESTING

#print(process_question(trainingData[2][0], questionModel))
#print(process_answer(trainingData[0][1][0], answer0Model, questionModel.initHidden()))
#print(process_answer(trainingData[3][1][0], answer0Model, questionModel.initHidden()))
#print(predict_answer(0, autograd.Variable(torch.randn(2, 10))))
question_model, answer_models = train(trainingData, 10)
accuracy1 = test(question_model, answer_models, trainingData, True)
print(accuracy1)
accuracy2 = test(question_model, answer_models, testData)
print(accuracy2)
#print(is_number("s"))
#print(is_number("4"))
#print(is_number(3))
#print(is_number("set out"))
#print(is_number([1, "s", "2"]))
