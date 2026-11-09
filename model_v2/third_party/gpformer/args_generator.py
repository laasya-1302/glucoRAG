# -*- coding: utf-8 -*-
"""
Created on Sat May 14 00:46:13 2022

@author: tz2916
"""

import argparse


def args_bglp(model = None):

    parser = argparse.ArgumentParser()
    

    
    # forecasting task
    parser.add_argument('--model', type=str, default=None, help='name of the model')
    parser.add_argument('--seq_len', type=int, default=72, help='input sequence length')
    parser.add_argument('--label_len', type=int, default=6, help='start token length')
    parser.add_argument('--pred_len', type=int, default=24, help='prediction sequence length')
    
    # model define
    parser.add_argument('--enc_in', type=int, default=1, help='encoder input size')
    parser.add_argument('--dec_in', type=int, default=1, help='decoder input size')
    parser.add_argument('--c_out', type=int, default=1, help='output size')
    parser.add_argument('--d_model', type=int, default=512, help='dimension of model')
    parser.add_argument('--n_heads', type=int, default=8, help='num of heads')
    parser.add_argument('--e_layers', type=int, default=1, help='num of encoder layers')
    parser.add_argument('--d_layers', type=int, default=1, help='num of decoder layers')
    parser.add_argument('--d_ff', type=int, default=2048, help='dimension of fcn')
    parser.add_argument('--factor', type=int, default=1, help='attn factor')
    parser.add_argument('--dropout', type=float, default=0.05, help='dropout')
    parser.add_argument('--embed', type=str, default='timeF', help='time features encoding')
    parser.add_argument('--activation', type=str, default='gelu', help='activation')
    parser.add_argument('--output_attention', action='store_true', help='whether to output attention in encoder')
    parser.add_argument('--num_workers', type=int, default=0, help='data loader num workers')
    parser.add_argument('--freq', type=str, default='cyc', help='freq for time features encoding')
    parser.add_argument('--scale_fn', type=int, default=0, help='type of scaler: 0 for no scaler, 1 for min-max, 2 for standardization')
    parser.add_argument('--ql', type=bool, default=False, help='quantile loss')
    parser.add_argument('--y_diff', type=bool, default=False, help='use glucose changes as targets (delta)')



    # GPU
    parser.add_argument('--use_gpu', type=bool, default=True, help='use gpu')
    parser.add_argument('--gpu', type=int, default=0, help='gpu')
    parser.add_argument('--use_multi_gpu', action='store_true', help='use multiple gpus', default=False)
    parser.add_argument('--devices', type=str, default='0,1,2,3', help='device ids of multile gpus')
    

    
    # MLDG
    parser.add_argument('--n_support_domains', type=int, default=1, help='Number of support domains sampled in each iteration')
    parser.add_argument('--n_query_domains', type=int, default=1, help='Number of query domains in each iteration')
    parser.add_argument('--trade-off', type=float, default=1,help='hyper parameter beta')
    parser.add_argument('--batch_size', type=int, default=36, help='batch size of train input data')
    parser.add_argument('--lr', '--learning-rate', default=0.001, type=float, help='initial learning rate', dest='lr')
    parser.add_argument('--momentum', default=0.9, type=float, help='momentum')
    parser.add_argument('--wd', '--weight-decay', default=0.0005, type=float, help='weight decay (default: 5e-4)')
    parser.add_argument('--iters_per_epoch', default=500, type=int, help='Number of iterations per epoch')
    parser.add_argument('--inner-iters', default=1, type=int,help='Number of iterations in inner loop')
    parser.add_argument('--train_epochs', type=int, default=1, help='train epochs')
    parser.add_argument('-p', '--print-freq', default=100, type=int, help='print frequency')



    args = parser.parse_args()
    args.model = model

    
    return args
    