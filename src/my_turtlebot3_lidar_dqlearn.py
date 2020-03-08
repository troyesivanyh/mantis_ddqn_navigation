#!/usr/bin/env python3

from my_gazebo_turtlebot3_dqlearn import GazeboTurtlebot3DQLearnEnv

import time
from distutils.dir_util import copy_tree
import os
import json
import random
import numpy as np
from keras.models import Sequential, load_model
from keras import optimizers
from keras.layers.core import Dense, Dropout, Activation
from keras.layers.normalization import BatchNormalization
from keras.layers.advanced_activations import LeakyReLU
from keras.regularizers import l2
from keras.layers import Input, Flatten, LSTM
from keras.models import Model
from keras.layers import concatenate, MaxPooling1D, Conv1D
import memory

class DeepQ:
    """
    DQN abstraction.

    As a quick reminder:
        traditional Q-learning:
            Q(s, a) += alpha * (reward(s,a) + gamma * max(Q(s') - Q(s,a))
        DQN:
            target = reward(s,a) + gamma * max(Q(s')

    """
    def __init__(self, inputs_laser, output_size, memorySize, discountFactor, learningRate, learnStart):
        """
        Parameters:
            - inputs_laser: inputs_laser size
            - outputs: output size
            - memorySize: size of the memory that will store each state
            - discountFactor: the discount factor (gamma)
            - learningRate: learning rate
            - learnStart: steps to happen before for learning. Set to 128
        """
        self.input_laser_size = inputs_laser
        self.output_size = output_size
        self.memory = memory.Memory(memorySize)
        self.discountFactor = discountFactor
        self.learnStart = learnStart
        self.learningRate = learningRate

        try:
            os.mkdir("/tmp/gazebo_gym_experiments/")
        except Exception:
            pass

    def initNetworks(self):
        model = self.createModel(self.output_size, self.learningRate)
        self.model = model

        targetModel = self.createModel(self.output_size, self.learningRate)
        self.targetModel = targetModel

    def createCNNModel(self, width, height, filters=(16, 32, 64), regress=False):
        inputShape = (height, width)
        chanDim = -1
        # define the model input
        inputs = Input(shape=inputShape)
        
        # loop over the number of filters
        for (i, f) in enumerate(filters):
            # if this is the first CONV layer then set the input
            # appropriately
            if i == 0:
                x = inputs
            # CONV => RELU => BN => POOL
            x = Conv1D(f, kernel_size=3, padding="same")(x)
            x = Activation("relu")(x)
            x = BatchNormalization(axis=chanDim)(x)
            x = MaxPooling1D(pool_size=2)(x)

        # flatten the volume, then FC => RELU => BN => DROPOUT
        x = Flatten()(x)
        x = Dense(16)(x)
        x = Activation("relu")(x)
        x = BatchNormalization(axis=chanDim)(x)
        x = Dropout(0.5)(x)
        # apply another FC layer, this one to match the number of nodes
        # coming out of the MLP
        x = Dense(4)(x)
        x = Activation("relu")(x)
        # check to see if the regression node should be added
        if regress:
            x = Dense(1, activation="linear")(x)
        # construct the CNN
        model = Model(inputs, x)
        # return the CNN
        return model

    def createMLPModel(self, dim, regress=False):
        # define our MLP network
        model = Sequential()
        model.add(Dense(8, input_dim=dim, activation="relu"))
        model.add(Dense(4, activation="relu"))
        # check to see if the regression node should be added
        if regress:
            model.add(Dense(1, activation="linear"))
        # return our model
        return model

    def createModel(self, output_size, learningRate):
        # create the MLP and CNN models
        cnn = self.createCNNModel(1, self.input_laser_size, regress=False)
        mlp = self.createMLPModel(2, regress=False) # x,y   2 value
        # create the input to our final set of layers as the *output* of both
        # the MLP and CNN
        combinedInput = concatenate([mlp.output, cnn.output])
        # our final FC layer head will have two dense layers, the final one
        # being our regression head
        x = Dense(4, activation="relu")(combinedInput)
        x = Dense(output_size, activation="softmax")(x)
        # our final model will accept categorical/numerical data on the MLP
        # input and images on the CNN input, outputting a single value (the
        # predicted price of the house)
        model = Model(inputs=[cnn.input, mlp.input], outputs=x)

        optimizer = optimizers.RMSprop(lr=learningRate, rho=0.9, epsilon=1e-06)
        model.compile(loss="mse", optimizer=optimizer)
        model.summary()
        return model


    def backupNetwork(self, model, backup):
        weightMatrix = []
        for layer in model.layers:
            weights = layer.get_weights()
            weightMatrix.append(weights)
        i = 0
        for layer in backup.layers:
            weights = weightMatrix[i]
            layer.set_weights(weights)
            i += 1

    def updateTargetNetwork(self):
        self.backupNetwork(self.model, self.targetModel)

    # predict Q values for all the actions
    def getQValues(self, state, targetPoints):
        # 1,180,1
        # batch_size , height, width
        predicted = self.model.predict([state.reshape(1,self.input_laser_size,1), targetPoints.reshape(1,len(targetPoints))])
        return predicted[0]

    def getTargetQValues(self, state, targetPoints):
        predicted = self.targetModel.predict([state.reshape(1,self.input_laser_size,1), targetPoints.reshape(1,len(targetPoints))])

        return predicted[0]

    def getMaxQ(self, qValues):
        return np.max(qValues)     # MAXIMUM DEGERI DONER

    def getMaxIndex(self, qValues):
        return np.argmax(qValues)  # ONEMLI MAXIMUM DEGERIN INDEXINI DONER

    # calculate the target function
    def calculateTarget(self, qValuesNewState, reward, isFinal):
        """
        target = reward(s,a) + gamma * max(Q(s')
        """
        if isFinal:
            return reward
        else : 
            return reward + self.discountFactor * self.getMaxQ(qValuesNewState)

    # select the action with the highest Q value
    def selectAction(self, qValues, explorationRate):
        rand = random.random()
        if rand < explorationRate :
            action = np.random.randint(1, 3)
        else :
            action = self.getMaxIndex(qValues)
        return action

    def selectActionByProbability(self, qValues, bias):
        qValueSum = 0
        shiftBy = 0
        for value in qValues:
            if value + shiftBy < 0:
                shiftBy = - (value + shiftBy)
        shiftBy += 1e-06

        for value in qValues:
            qValueSum += (value + shiftBy) ** bias

        probabilitySum = 0
        qValueProbabilities = []
        for value in qValues:
            probability = ((value + shiftBy) ** bias) / float(qValueSum)
            qValueProbabilities.append(probability + probabilitySum)
            probabilitySum += probability
        qValueProbabilities[len(qValueProbabilities) - 1] = 1

        rand = random.random()
        i = 0
        for value in qValueProbabilities:
            if (rand <= value):
                return i
            i += 1

    def addMemory(self, state, targetPoints, action, reward, newState, newTargetPoints, isFinal):
        self.memory.addMemory(state, targetPoints, action, reward, newState, newTargetPoints, isFinal)

    def learnOnLastState(self):
        if self.memory.getCurrentSize() >= 1:
            return self.memory.getMemory(self.memory.getCurrentSize() - 1)

    def learnOnMiniBatch(self, miniBatchSize, useTargetNetwork=True):
        # Do not learn until we've got self.learnStart samples        
        if self.memory.getCurrentSize() > self.learnStart:
            # learn in batches of 128
            miniBatch = self.memory.getMiniBatch(miniBatchSize)
            X_laser_batch = np.empty((0,self.input_laser_size,1), dtype = np.float64)  # 0 batch baslangicta hic elemena sahip olmadigi icin
            X_targetPoint_batch = np.empty((0,2), dtype = np.float64)
            Y_batch = np.empty((0,self.output_size), dtype = np.float64)
            for sample in miniBatch:
                isFinal = sample['isFinal']
                state = sample['state']
                targetPoints = sample['targetPoints']
                action = sample['action']
                reward = sample['reward']
                newState = sample['newState']
                newTargetPoints = sample['newTargetPoints']

                qValues = self.getQValues(state ,targetPoints)
                if useTargetNetwork:
                    qValuesNewState = self.getTargetQValues(newState, newTargetPoints)
                else :
                    qValuesNewState = self.getQValues(newState, newTargetPoints)
                targetValue = self.calculateTarget(qValuesNewState, reward, isFinal)
                X_laser_batch = np.append(X_laser_batch, np.array([state.copy()]), axis=0)
                X_targetPoint_batch = np.append(X_targetPoint_batch, np.array([targetPoints.copy()]), axis=0)
                Y_sample = qValues.copy()
                Y_sample[action] = targetValue
                Y_batch = np.append(Y_batch, np.array([Y_sample]), axis=0)
                if isFinal:
                    X_laser_batch = np.append(X_laser_batch, np.array([newState.copy()]), axis=0)
                    X_targetPoint_batch = np.append(X_targetPoint_batch, np.array([newTargetPoints.copy()]), axis=0)
                    Y_batch = np.append(Y_batch, np.array([[reward]*self.output_size]), axis=0)
            self.model.fit([X_laser_batch, X_targetPoint_batch], Y_batch, batch_size = len(miniBatch), nb_epoch=1, verbose = 0)

    def saveModel(self, path):
        self.model.save(path)

    def loadWeights(self, path):
        self.model.set_weights(load_model(path).get_weights())

def detect_monitor_files(training_dir):
    return [os.path.join(training_dir, f) for f in os.listdir(training_dir) if f.startswith('openaigym')]

def clear_monitor_files(training_dir):
    files = detect_monitor_files(training_dir)
    if len(files) == 0:
        return
    for file in files:
        print (file)
        os.unlink(file)

if __name__ == '__main__':
    env = GazeboTurtlebot3DQLearnEnv()
    #REMEMBER!: turtlebot_nn_setup.bash must be executed.
    outdir = '/tmp/gazebo_gym_experiments/'

    continue_execution = False
    #fill this if continue_execution=True

    weights_path = '/tmp/turtle_c2_dqn_ep200.h5' 
    monitor_path = '/tmp/turtle_c2_dqn_ep200'
    params_json  = '/tmp/turtle_c2_dqn_ep200.json'

    if not continue_execution:
        #Each time we take a sample and update our weights it is called a mini-batch. 
        #Each time we run through the entire dataset, it's called an epoch.
        #PARAMETER LIST
        epochs = 10000
        steps = 10000
        updateTargetNetwork = 10000
        explorationRate = 1
        minibatch_size = 64
        learnStart = 64
        learningRate = 0.00025
        discountFactor = 0.99
        memorySize = 1000000
        network_laser_inputs = 180
        output_size = 3 # Three actions we have
        current_epoch = 0

        deepQ = DeepQ(network_laser_inputs, output_size, memorySize, discountFactor, learningRate, learnStart)
        deepQ.initNetworks()
    else:
        #Load weights, monitor info and parameter info.
        #ADD TRY CATCH fro this else
        print("Continue to learning from old files")
        time.sleep(5)
        with open(params_json) as outfile:
            d = json.load(outfile)
            epochs = d.get('epochs')
            steps = d.get('steps')
            updateTargetNetwork = d.get('updateTargetNetwork')
            explorationRate = d.get('explorationRate')
            minibatch_size = d.get('minibatch_size')
            learnStart = d.get('learnStart')
            learningRate = d.get('learningRate')
            discountFactor = d.get('discountFactor')
            memorySize = d.get('memorySize')
            network_laser_inputs = d.get('network_laser_inputs')
            output_size = d.get('output_size')
            current_epoch = d.get('current_epoch')

        deepQ = DeepQ(network_laser_inputs, output_size, memorySize, discountFactor, learningRate, learnStart)
        deepQ.initNetworks()
        deepQ.loadWeights(weights_path)

        clear_monitor_files(outdir)
        copy_tree(monitor_path,outdir)

    last100Scores = [0] * 100
    last100ScoresIndex = 0
    last100Filled = False
    stepCounter = 0
    highest_reward = 0

    start_time = time.time()

    #start iterating from 'current epoch'.

    for epoch in range(current_epoch+1, epochs+1, 1):
        observation, targetPoints = env.reset()
        cumulated_reward = 0

        # number of timesteps
        for t in range(steps):
            # env.render()
            qValues = deepQ.getQValues(observation, targetPoints)

            action = deepQ.selectAction(qValues, explorationRate)

            newObservation, newTargetPoints, reward, done, info = env.step(action)

            cumulated_reward += reward
            if highest_reward < cumulated_reward:
                highest_reward = cumulated_reward

            deepQ.addMemory(observation, targetPoints, action, reward, newObservation, newTargetPoints, done)

            if stepCounter >= learnStart:
                if stepCounter <= updateTargetNetwork:
                    deepQ.learnOnMiniBatch(minibatch_size, False)
                else :
                    deepQ.learnOnMiniBatch(minibatch_size, True)

            observation = newObservation
            targetPoints = newTargetPoints

            if (t >= 1000):
                print ("reached the end! :D")
                done = True

            if done:
                last100Scores[last100ScoresIndex] = t
                last100ScoresIndex += 1
                if last100ScoresIndex >= 100:
                    last100Filled = True
                    last100ScoresIndex = 0
                if not last100Filled:
                    print ("EP "+str(epoch)+" - {} timesteps".format(t+1)+"   Exploration="+str(round(explorationRate, 2)))
                else :
                    m, s = divmod(int(time.time() - start_time), 60)
                    h, m = divmod(m, 60)
                    print ("EP "+str(epoch)+" - {} timesteps".format(t+1)+" - last100 Steps : "+str((sum(last100Scores)/len(last100Scores)))+" - Cumulated R: "+str(cumulated_reward)+"   Eps="+str(round(explorationRate, 2))+"     Time: %d:%02d:%02d" % (h, m, s))
                    if (epoch)%100==0:
                        #save model weights and monitoring data every 100 epochs. 
                        deepQ.saveModel('/tmp/turtle_c2_dqn_ep'+str(epoch)+'.h5')

                        copy_tree(outdir,'/tmp/turtle_c2_dqn_ep'+str(epoch))
                        #save simulation parameters.
                        parameter_keys = ['epochs','steps','updateTargetNetwork','explorationRate','minibatch_size','learnStart','learningRate','discountFactor','memorySize','network_laser_inputs','current_epoch']
                        parameter_values = [epochs, steps, updateTargetNetwork, explorationRate, minibatch_size, learnStart, learningRate, discountFactor, memorySize, network_laser_inputs, epoch]
                        parameter_dictionary = dict(zip(parameter_keys, parameter_values))
                        with open('/tmp/turtle_c2_dqn_ep'+str(epoch)+'.json', 'w') as outfile:
                            json.dump(parameter_dictionary, outfile)
                break

            stepCounter += 1
            if stepCounter % updateTargetNetwork == 0:
                deepQ.updateTargetNetwork()
                print ("updating target network")

        explorationRate *= 0.995 #epsilon decay
        # explorationRate -= (2.0/epochs)
        explorationRate = max (0.05, explorationRate)
