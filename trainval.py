import sls
import torch
import torchvision
import tqdm
import pandas as pd
import pprint 
import itertools
import os
import pylab as plt
import configs 

from src import models
from src import datasets
from src import optimizers
from src import utils as ut

import argparse

from torch.nn import functional as F
from torch.utils.data import DataLoader


def trainval(exp_dict, savedir, datadir):
    pprint.pprint(exp_dict)

    # Load Dataset
    train_set = datasets.get_dataset(dataset_name=exp_dict["dataset"], 
                                     datadir=datadir)
    train_loader = DataLoader(train_set, drop_last=True, shuffle=True, batch_size=128)

    # Load model
    model = models.get_model(exp_dict["model"]).cuda()

    # Load Optimizer
    opt = optimizers.get_optimizer(exp_dict["opt"], model.parameters())

    if exp_dict["opt"] in ["sgd_armijo"]:
        requires_closure = True
    else:
        requires_closure = False

    # Resume from last saved state_dict
    if not os.path.exists(savedir + "/score_list.pkl"):
        score_list = []
    else:
        score_list = ut.load_pkl(savedir + "/score_list.pkl")
        model.load_state_dict(torch.load(savedir + "/model_state_dict.pth"))
        opt.load_state_dict(torch.load(savedir + "/opt_state_dict.pth"))

    for epoch in range(exp_dict["max_epoch"]):
        # =================================
        # 1. Compute metrics over train loader
        model.eval()
        print("Evaluating Epoch %d" % epoch)

        loss_sum = 0.
        for images, labels in tqdm.tqdm(train_loader):
            images, labels = images.cuda(), labels.cuda()

            with torch.no_grad():
                loss_sum += compute_loss(model, images, labels)

        train_loss = float(loss_sum / len(train_set))
        score_list += [{"train_loss":train_loss, "epoch":epoch}]

        # =================================
        # 2. Train over train loader
        model.train()
        print("Training Epoch %d" % epoch)

        for images,labels in tqdm.tqdm(train_loader):
            images, labels = images.cuda(), labels.cuda()

            opt.zero_grad()

            if requires_closure:
                closure = lambda : compute_loss(model, images, labels)
                opt.step(closure)
            else:
                loss = compute_loss(model, images, labels)
                loss.backward()
                opt.step()

        # report and save
        print(pd.DataFrame(score_list))
        ut.save_pkl(savedir + "/score_list.pkl", score_list)
        ut.torch_save(savedir + "/model_state_dict.pth", model.state_dict())
        ut.torch_save(savedir + "/opt_state_dict.pth", opt.state_dict())
    
    return score_list

def compute_loss(model, images, labels):
    probs = F.log_softmax(model(images), dim=1)
    loss = F.nll_loss(probs, labels, reduction="sum")

    return loss

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument('-e', '--exp_group_name', default='mnist')
    
    parser.add_argument('-sb', '--savedir_base', default= configs.SAVEDIR_PATH + '/experiments/')
    parser.add_argument('-d', '--datadir', default= configs.SAVEDIR_PATH + '/datasets/')

    parser.add_argument("-r", "--reset",  default=0, type=int)
   
    args = parser.parse_args()

    exp_list = \
            ut.cartesian_exp_group(
                configs.EXP_GROUPS[args.exp_group_name])

    # loop over optimizers
    for exp_dict in exp_list:
        exp_id = ut.hash_dict(exp_dict)
        savedir = args.savedir_base + "/%s/" % exp_id
        os.makedirs(savedir, exist_ok=True)

         # check if experiment exists
        if args.reset:
            if os.path.exists(savedir + "/score_list.pkl"):
                os.remove(savedir + "/score_list.pkl")

        # do trainval
        trainval(exp_dict=exp_dict, savedir=savedir, datadir=args.datadir)
        
