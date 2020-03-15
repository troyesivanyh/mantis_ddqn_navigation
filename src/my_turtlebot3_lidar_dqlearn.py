#!/usr/bin/env python3

from my_gazebo_turtlebot3_dqlearn import MantisGymEnv

import time
import os
import json
import random
import numpy as np
from keras.models import Sequential, load_model
from keras.optimizers import RMSprop
from keras.layers import Dense, Dropout
from collections import deque

class Agent:

    def __init__(self, stateSize, actionSize):
        self.loadModel = False  # Load model from file
        self.loadEpisodeFrom = 0  # Start to learn from this episode
        self.episodeCount = 10000  # Total episodes
        self.stateSize = stateSize  # Step size get from env
        self.actionSize = actionSize  # Action size get from env
        self.targetUpdateCount = 2000  # Update target model at every targetUpdateCount
        self.saveModelAtEvery = 20  # Save model at every saveModelAtEvery epoch
        self.discountFactor = 0.99  # For qVal calculations
        self.learningRate = 0.00025  # For model
        self.epsilon = 1.0  # Exploit or Explore?
        self.epsilonDecay = 0.99  # epsilon will multiplicated with this thing in every epoch
        self.epsilonMin = 0.05  # Epsilon never fall more then this
        self.batchSize = 64  # Size of a miniBatch
        self.learnStart = 64  # Start to train model from this step
        self.memory = deque(maxlen=1000000)  # Main memory to keep batchs
        self.timeOutLim = 500  # After this end the epoch

        self.model = self.initNetwork()
        self.targetModel = self.initNetwork()

        self.updateTargetModel()

        self.savePath = '/tmp/mantisModel/'
        try:
            os.mkdir(self.savePath)
        except Exception:
            pass

    def initNetwork(self):
        model = Sequential()

        model.add(Dense(64, input_shape=(self.stateSize,), activation="relu", kernel_initializer="lecun_uniform"))

        model.add(Dense(64, activation="relu", kernel_initializer="lecun_uniform"))
        model.add(Dropout(0.3))
        model.add(Dense(self.actionSize, activation="linear", kernel_initializer="lecun_uniform"))
        model.compile(loss="mse", optimizer=RMSprop(lr=self.learningRate, rho=0.9, epsilon=1e-06))
        model.summary()

        return model

    def calcQ(self, reward, nextTarget, done):
        """
        traditional Q-learning:
            Q(s, a) += alpha * (reward(s,a) + gamma * max(Q(s') - Q(s,a))
        DQN:
            target = reward(s,a) + gamma * max(Q(s')

        """
        if done:
            return reward
        else:
            return reward + self.discountFactor * np.amax(nextTarget)

    def updateTargetModel(self):
        self.targetModel.set_weights(self.model.get_weights())

    def calcAction(self, state):
        if np.random.rand() <= self.epsilon:
            self.qValue = np.zeros(self.actionSize)
            return random.randrange(self.actionSize)
        else:
            qValue = self.model.predict(state.reshape(1, self.stateSize))
            self.qValue = qValue
            return np.argmax(qValue[0])
    
    def appendMemory(self, state, action, reward, nextState, done):
        self.memory.append((state, action, reward, nextState, done))

    def trainModel(self, target=False):
        miniBatch = random.sample(self.memory, self.batchSize)
        xBatch = np.empty((0, self.stateSize), dtype=np.float64)
        yBatch = np.empty((0, self.actionSize), dtype=np.float64)

        for i in range(self.batchSize):
            state = miniBatch[i][0]
            action = miniBatch[i][1]
            reward = miniBatch[i][2]
            nextState = miniBatch[i][3]
            done = miniBatch[i][4]

            qValue = self.model.predict(state.reshape(1, len(state)))
            self.qValue = qValue

            if target:
                nextTarget = self.targetModel.predict(nextState.reshape(1, len(nextState)))

            else:
                nextTarget = self.model.predict(nextState.reshape(1, len(nextState)))

            nextQValue = self.calcQ(reward, nextTarget, done)

            xBatch = np.append(xBatch, np.array([state.copy()]), axis=0)
            ySample = qValue.copy()

            ySample[0][action] = nextQValue
            yBatch = np.append(yBatch, np.array([ySample[0]]), axis=0)

            if done:
                xBatch = np.append(xBatch, np.array([nextState.copy()]), axis=0)
                yBatch = np.append(yBatch, np.array([[reward] * self.actionSize]), axis=0)

        self.model.fit(xBatch, yBatch, batch_size=self.batchSize, epochs=1, verbose=0)


if __name__ == '__main__':
    env = MantisGymEnv()
    stateSize = env.stateSize
    actionSize = env.actionSize

    agent = Agent(stateSize, actionSize)

    continueFromFiles = False
    agent.loadEpisodeFrom = 0
    if continueFromFiles:
        agent.model.set_weights(load_model(agent.savePath+str(agent.loadEpisodeFrom)+".h5").get_weights())

        with open(agent.savePath+str(agent.loadEpisodeFrom)+'.json') as outfile:
            param = json.load(outfile)
            agent.epsilon = param.get('epsilon')

    stepCounter = 0

    startTime = time.time()

    for epoch in range(agent.loadEpisodeFrom + 1, agent.episodeCount):
        done = False
        state = env.reset()
        score = 0

        for t in range(999999):
            action = agent.calcAction(state)
            nextState, reward, done = env.step(action)
            agent.appendMemory(state, action, reward, nextState, done)

            if len(agent.memory) >= agent.learnStart:
                if stepCounter <= agent.targetUpdateCount:
                    agent.trainModel(False)
                else:
                    agent.trainModel(True)

            score += reward
            state = nextState
            
            if epoch % agent.saveModelAtEvery == 0:
                weightsPath = agent.savePath + str(epoch) + '.h5'
                paramPath = agent.savePath + str(epoch) + '.json'
                print("Saving model as " + weightsPath[-3:])
                agent.model.save(weightsPath)
                with open(paramPath, 'w') as outfile:
                    json.dump(paramDictionary, outfile)

            if (t >= agent.timeOutLim):
                print("Time out")
                done = True

            if done:
                agent.updateTargetModel()
                m, s = divmod(int(time.time() - startTime), 60)
                h, m = divmod(m, 60)

                print('Ep:'+str(epoch)+' score: '+str(score)+' memory: '+str(len(agent.memory))+' epsilon: '+str(agent.epsilon)+' time: '+str(h)+':'+str(m)+':'+str(s))
                paramKeys = ['epsilon']
                paramValues = [agent.epsilon]
                paramDictionary = dict(zip(paramKeys, paramValues))
                break

            stepCounter += 1
            if stepCounter % agent.targetUpdateCount == 0:
                print("UPDATE TARGET NETWORK")

        if agent.epsilon > agent.epsilonMin:
            agent.epsilon *= agent.epsilonDecay

"""
Problem 1 = TragetUpdate ne olaki neden sadece print var
Problem 2 = Done olunca qValue reward * actionSize oluyor. Ben hedefe ulasinca da done true ettigim icin bir sorun olur mu ki
Problem 3 = neden max q sadece secilen aksiyon ile degistiriliyor
"""