# -*- coding: utf-8 -*-
"""
Created on Tue Mar 21 11:37:53 2023

@author: tz2916
"""

import os
import torch
import time
import random
import pickle
import numpy as np
import higher



from utils.data import ForeverDataIterator
from utils.meter import AverageMeter, ProgressMeter
from layers.utils import QuantileLoss
from args_generator import args_bglp
from models import  GPFormer
from torch import optim, nn


model_dict = {
    'GPFormer':GPFormer
}
quantiles = [ 0.1, 0.25, 0.5, 0.75, 0.9]
ql_loss = QuantileLoss()


def validate(val_loader, model, args, device,flag,criterion=ql_loss) -> float:
    # switch to evaluate mode
    model.eval()
    f_dim = 0
    preds = []
    trues = []
    with torch.no_grad():        
        for i, (batch_x, batch_y, batch_x_mark, batch_y_mark) in enumerate(val_loader):

            batch_x = batch_x.float().to(device)
            batch_y = batch_y.float().to(device)
            batch_x_mark = batch_x_mark.float().to(device)
            batch_y_mark = batch_y_mark.float().to(device)
            
            if args.y_diff:
                delta_trend =  batch_x[:,args.seq_len-args.label_len-1,:1].unsqueeze(1).repeat(1, (args.label_len+args.pred_len), 1)
                batch_y = batch_y-delta_trend
            
            # decoder input
            dec_inp = torch.zeros_like(batch_y[:, -args.pred_len:, :]).float()
            dec_inp = torch.cat([batch_y[:, :args.label_len, :], dec_inp], dim=1).float().to(device)
            
            # compute output
            outputs = model(batch_x, batch_x_mark, dec_inp, batch_y_mark, batch_y)
            batch_y = batch_y[:, -args.pred_len:, f_dim:]
            outputs = outputs[:, -args.pred_len:, f_dim:]
            
            if args.y_diff:
                batch_y = batch_y+delta_trend[:, -args.pred_len:, :]
                outputs = outputs+delta_trend[:, -args.pred_len:, :]
                

                            
            pred = ql_loss.to_prediction(outputs).detach().cpu().numpy()
            true = batch_y.detach().cpu().numpy()
            pred = pred*args.scale+args.delta
            true = true*args.scale+args.delta       
                            
            preds.append(pred)
            trues.append(true)
            
    preds_all, tures_all = np.vstack(preds),np.vstack(trues)
    return preds_all,tures_all



def random_split(x_list, y_list,x_mark_list,y_mark_list, n_domains_per_batch, n_support_domains):
    assert n_support_domains < n_domains_per_batch

    support_domain_idxes = random.sample(range(n_domains_per_batch), n_support_domains)
    support_domain_list = [(x_list[idx], y_list[idx],x_mark_list[idx],y_mark_list[idx]) for idx in range(n_domains_per_batch) if
                            idx in support_domain_idxes]
    query_domain_list = [(x_list[idx], y_list[idx],x_mark_list[idx],y_mark_list[idx]) for idx in range(n_domains_per_batch) if
                          idx not in support_domain_idxes]

    return support_domain_list, query_domain_list


def train(train_iter, model, optimizer, lr_scheduler, epoch, 
          n_domains_per_batch, args, criterion=ql_loss):
    batch_time = AverageMeter('Time', ':4.2f')
    losses = AverageMeter('Loss', ':3.2f')
    meta_30_rmse = AverageMeter('Query 30 min RMSE', ':3.1f')
    meta_60_rmse = AverageMeter('Query 60 min RMSE', ':3.1f')
    meta_120_rmse = AverageMeter('Query 120 min RMSE', ':3.1f')
    
    progress = ProgressMeter(
        args.iters_per_epoch,
        [batch_time, losses, meta_30_rmse,meta_60_rmse,meta_120_rmse],
        prefix="Epoch: [{}]".format(epoch))

    # switch to train mode
    model.train()
    device = args.device
    f_dim = 0
    end = time.time()
    for i in range(args.iters_per_epoch):
        batch_x, batch_y, batch_x_mark, batch_y_mark = next(train_iter)
        batch_x = batch_x.float().to(device)
        batch_y = batch_y.float().to(device)
        batch_x_mark = batch_x_mark.float().to(device)
        batch_y_mark = batch_y_mark.float().to(device)
        
        if args.y_diff:
            batch_y = batch_y - batch_x[:,args.seq_len-args.label_len-1,:1].unsqueeze(1).repeat(1, (args.label_len+args.pred_len), 1)

        # split into support domain and query domain
        x_list = batch_x.chunk(n_domains_per_batch, dim=0)
        y_list = batch_y.chunk(n_domains_per_batch, dim=0)
        
        x_mark_list = batch_x_mark.chunk(n_domains_per_batch, dim=0)
        y_mark_list = batch_y_mark.chunk(n_domains_per_batch, dim=0)        
        
        
        support_domain_list, query_domain_list = random_split(x_list, y_list,x_mark_list,y_mark_list, n_domains_per_batch,
                                                              args.n_support_domains)
        # clear grad
        optimizer.zero_grad()

        # compute output
        with higher.innerloop_ctx(model, optimizer, copy_initial_weights=False) as (inner_model, inner_optimizer):
            # perform inner optimization
            for _ in range(args.inner_iters):
                loss_inner = 0
                for (x_s,y_s,x_mark_s,y_mark_s) in support_domain_list:
                    # decoder input
                    dec_inp = torch.zeros_like(y_s[:, -args.pred_len:, :]).float()
                    dec_inp_s = torch.cat([y_s[:, :args.label_len, :], dec_inp], dim=1).float().to(device)
                    outputs = inner_model(x_s, x_mark_s, dec_inp_s, y_mark_s, y_s)
                    # normalize loss by support domain num
                    y_s = y_s[:, -args.pred_len:, f_dim:].to(device)
                    outputs = outputs[:, -args.pred_len:, f_dim:]
                    loss_inner += criterion(outputs, y_s)/ args.n_support_domains


                inner_optimizer.step(loss_inner)

            # calculate outer loss
            loss_outer = 0
            rmse30, rmse60, rmse120 = 0, 0, 0

            
            # loss on support domains
            for (x_s,y_s,x_mark_s,y_mark_s)  in support_domain_list:
                # decoder input
                dec_inp = torch.zeros_like(y_s[:, -args.pred_len:, :]).float()
                dec_inp_s = torch.cat([y_s[:, :args.label_len, :], dec_inp], dim=1).float().to(device)
                outputs = model(x_s, x_mark_s, dec_inp_s, y_mark_s, y_s)
                # normalize loss by support domain num
                y_s = y_s[:, -args.pred_len:, f_dim:].to(device)
                outputs = outputs[:, -args.pred_len:, f_dim:]
                loss_outer +=  criterion(outputs, y_s)/ args.n_support_domains

            # loss on query domains
            for (x_q,y_q,x_mark_q,y_mark_q) in query_domain_list:
                # decoder input
                dec_inp = torch.zeros_like(y_q[:, -args.pred_len:, :]).float()
                dec_inp_q = torch.cat([y_q[:, :args.label_len, :], dec_inp], dim=1).float().to(device)
                outputs = inner_model(x_q, x_mark_q, dec_inp_q, y_mark_q, y_q)
                
                # normalize loss by query domain num
                y_q = y_q[:, -args.pred_len:, f_dim:].to(device)
                outputs = outputs[:, -args.pred_len:, f_dim:]
                
                loss_outer += criterion(outputs, y_q) * args.trade_off / args.n_query_domains
                
                pred = ql_loss.to_prediction(outputs).detach().cpu().numpy()
                true = y_q.detach().cpu().numpy()
                
                pred = pred*args.scale+args.delta
                true = true*args.scale+args.delta

                # pred_metrics(pred,true,args)
                    
                rmse30 += np.sqrt(np.mean((pred[:,5,0]-true[:,5,0])**2)) / args.n_query_domains
                rmse60 += np.sqrt(np.mean((pred[:,11,0]-true[:,11,0])**2)) / args.n_query_domains
                rmse120 += np.sqrt(np.mean((pred[:,23,0]-true[:,23,0])**2)) / args.n_query_domains

        # update statistics
        losses.update(loss_outer.item(), args.batch_size)
        meta_30_rmse.update(rmse30, args.batch_size)
        meta_60_rmse.update(rmse60, args.batch_size)
        meta_120_rmse.update(rmse120, args.batch_size)
        
        # compute gradient and do SGD step
        loss_outer.backward()
        optimizer.step()
        lr_scheduler.step()

        # measure elapsed time
        batch_time.update(time.time() - end)
        end = time.time()
        
        if i % args.print_freq == 0:
            progress.display(i)



#%%  
if __name__ == '__main__':         
    args = args_bglp(model='GPFormer')
    
    if args.use_gpu:
        device = torch.device('cuda:{}'.format(args.gpu))
        print('-------------Use GPU: cuda:{}-------------'.format(args.gpu))
    else:
        device = torch.device('cpu')
        print('-------------Use CPU-------------')
        
    args.device = device


    print('-------------Creating model-------------:')
    model = model_dict[args.model].Model(args).float().to(device)

    if args.use_multi_gpu and args.use_gpu:
        model = nn.DataParallel(model, device_ids=args.device_ids)
        
    # define optimizer and lr scheduler
    optimizer = optim.SGD(model.parameters(), args.lr, momentum=args.momentum, weight_decay=args.wd,
                    nesterov=True)
    lr_scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, args.train_epochs * args.iters_per_epoch)

    model_path = f'saved_models/{args.model}'
    if (not os.path.exists(model_path)):
        os.makedirs(model_path)

    print('-------------Loading data-------------:')
    n_domains_per_batch = args.n_support_domains + args.n_query_domains
    scaler_fitted  = pickle.load(open("data_loader/mldg_scaler.pkl", "rb" ))
    args.scale,args.delta  = scaler_fitted.scale_[0],scaler_fitted.mean_[0]  
    train_loader = torch.load('data_loader/mldg_train_loader.pth') 
    test_loader = torch.load('data_loader/mldg_test_loader.pth') 
    train_iter = ForeverDataIterator(train_loader)

    print('-------------Training-------------:')
    for epoch in range(args.train_epochs):
        with torch.backends.cudnn.flags(enabled=False): 
            train(train_iter, model, optimizer, lr_scheduler, epoch, n_domains_per_batch, args)
    
    
    print("-------------Testing-------------:")
    preds_all_tes,trues_all_tes = validate(test_loader, model, args, device,flag='Test')  


    print("---------Save model---------:")
    torch.save(model, model_path)




   
            
