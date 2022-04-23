import sys;sys.path.append('../utils')
import analyse_model
import pylab
import organiser
from organiser import memoized
from copy import deepcopy
from simulate_experiment import get_simulated_data
import plotting_functions as plotting
import spiketools
import analyses
import joe_and_lili
from general_func import *


def integrate(counts,tau = 50.,dt = 1.):
    print('tau: ',tau)
    integral = pylab.zeros_like(counts).astype(float)
    for t in range(1,counts.shape[1]):
        integral[:,t] = integral[:,t-1] + dt * (-integral[:,t-1]/float(tau) + counts[:,t-1])


    return integral


def get_count_integrals(params,tau = 100.,integrate_from_go  =False,normalise_across_clusters = False):
    
    cluster_params = deepcopy(params)
    try:
        cluster_params.pop('condition')
    except:
        pass
    cluster_counts,time,conditions,directions = analyse_model.get_mean_cluster_counts(cluster_params)
    if integrate_from_go:
        go_time = params['sim_params'].get('prep_length',1000)
        go_ind = pylab.argmin(pylab.absolute(time-go_time))
        integrals  = pylab.array([integrate(counts[:,go_ind:],tau  =tau) for counts in cluster_counts])
        intshape = integrals.shape
        timeshape = time.shape[0]
        diff = timeshape - intshape[2]
        integrals = pylab.append(pylab.zeros((intshape[0],intshape[1],diff)), integrals,axis=2)


    else:
        integrals = pylab.array([integrate(counts,tau  =tau) for counts in cluster_counts])
   
    try:
        condition = params['condition']
        integrals = integrals[:,conditions==condition]
        directions = directions[conditions == condition]
        conditions = conditions[conditions == condition]

        
    except:
        pass


    # normalise
    if normalise_across_clusters:
        integrals[integrals==0] = 1e-10
        integrals /= integrals.sum(axis=0)[None,:,:]
    else:
        
        cluster_max = integrals.max(axis=2).max(axis=1)
        integrals /= cluster_max[:,None,None]

        
    return integrals,time,conditions,directions



def race_to_threshold(params,tau = 100.,threshold = 0.5,integral_output = None,integrate_from_go = False,normalise_across_clusters = True):
    if integral_output is None:
        full_integrals,time,conditions,directions = get_count_integrals(params,tau ,integrate_from_go = integrate_from_go,normalise_across_clusters=normalise_across_clusters)
    else:
        full_integrals,time,conditions,directions = integral_output

    
    


    # Go cue
    go_time = params['sim_params'].get('prep_length',1000)
    go_ind = pylab.argmin(pylab.absolute(time-go_time))
    integrals = full_integrals[:,:,go_ind:]
    
    prediction = []
    rts = []
    
    for trial in range(integrals.shape[1]):
        trial_ints = integrals[:,trial]
       
        max_trial_int = trial_ints.max(axis=0)
        t = find(max_trial_int>threshold)
        if len(t)>0:
            direction = float(pylab.argmax(trial_ints[:,t[0]])+1)
            rt = float(t[0])
        else:
            direction  =0
            rt = 10000
               

        prediction.append(direction)
        rts.append(rt)
        


    return pylab.array(prediction),pylab.array(rts),conditions,directions,full_integrals,time


def _calc_thresh_scores(params):
    
    race_params = deepcopy(params)
    thresh_range = race_params.pop('thresh_range')
    tau = race_params.pop('tau')
    integrate_from_go = params.pop('integrate_from_go')
    normalise_across_clusters = params.pop('normalise_across_clusters')
    try:
        reps = race_params.pop('reps')
    except:
        reps = 1
    scores = []
    print('caclulatining threshold scores')
    
    integral_output = get_count_integrals(params,tau ,integrate_from_go = integrate_from_go,normalise_across_clusters=normalise_across_clusters)
    for threshold in thresh_range:

        predictions,rts,conditions,directions,_,_ = race_to_threshold(race_params,tau = tau,threshold=threshold,integral_output = integral_output,normalise_across_clusters=normalise_across_clusters)

        finite = pylab.isfinite(predictions)

        predictions = predictions[finite]
        directions = directions[finite]
        if len(directions)<1:
            repscores = [pylab.nan]
        else:
            if reps>1:
                repscores = []
                for r in range(reps):
                    
                    inds = pylab.randint(0,len(directions),len(directions))
                    repscores.append(analyse_model.balanced_accuray(predictions[inds],directions[inds]))
            else:
                repscores = analyse_model.balanced_accuray(predictions,directions)
        scores.append(pylab.nanmean(repscores))

    return pylab.array(thresh_range),pylab.array(scores)

def optimize_threshold(params,tau=100,thresh_range = pylab.arange(0,1.0,0.1),redo = False,reps  =10,integrate_from_go  =False,normalise_across_clusters = False):
    
    calc_params = deepcopy(params)
    calc_params['thresh_range'] = thresh_range
    calc_params['tau'] = tau
    calc_params['reps'] = reps
    calc_params['integrate_from_go'] = integrate_from_go
    calc_params['normalise_across_clusters'] = normalise_across_clusters
    return organiser.check_and_execute(calc_params,_calc_thresh_scores,'race_to_threshold_scores',redo  =redo)
   







def _calc_reaction_time_analysis(original_params):
    
    params = deepcopy(original_params)
    
    tau  =params.pop('tau')
    threshold_per_condition = params.pop('threshold_per_condition')
    threshold_resolution = params.pop('threshold_resolution')
    score_reps = params.pop('score_reps')
    integrate_from_go = params.pop('integrate_from_go')
    normalise_across_clusters = params.pop('normalise_across_clusters')
    try:
        redo = params.pop('redo')
    except:
        redo  =False
    
    all_predictions = []
    all_rts = []
    all_conditions = []
    all_directions = []
    condition_thresholds = {}
    condition_threshold_scores = {}
    all_integrals = None
    for condition in [1,2,3]:
        
        params['condition'] = condition
        
        opt_params = deepcopy(params)
        if not threshold_per_condition:
            opt_params.pop('condition')
        thresh_range,scores = optimize_threshold(opt_params,tau  =tau,thresh_range=pylab.arange(0,1.0,threshold_resolution),reps =score_reps,redo = redo,integrate_from_go = integrate_from_go,normalise_across_clusters=normalise_across_clusters)
        condition_threshold_scores[condition] = (thresh_range,scores)
        params['condition'] = condition
        
        print(thresh_range)
        print(scores)
        finite = pylab.isfinite(scores)
        thresh_range = thresh_range[finite]
        scores= scores[finite]
        threshold = thresh_range[pylab.argmax(scores)]

        condition_thresholds[condition] = threshold
        predictions,rts,conditions,directions,integrals,time = race_to_threshold(params,threshold = threshold,tau  =tau,integrate_from_go  =integrate_from_go,normalise_across_clusters=normalise_across_clusters)
        #print rts
        all_predictions += predictions.tolist()
        all_rts += rts.tolist()
        all_conditions += conditions.tolist()
        all_directions += directions.tolist()
        if all_integrals is None:
            all_integrals = integrals
        else:
            all_integrals = pylab.append(all_integrals, integrals,axis=1)

    result = {'condition_thresholds':condition_thresholds,'condition_threshold_scores':condition_threshold_scores,
              'predictions':pylab.array(all_predictions),'rts':pylab.array(all_rts),'conditions':pylab.array(all_conditions),'directions':pylab.array(all_directions),
              'integrals':all_integrals,'time':time}

    print(condition_thresholds)
    return result
    


    

        




def get_reaction_time_analysis(original_params,threshold_per_condition = False,tlim = [-500,2000],tau = 10.,threshold_resolution = 0.01,score_reps =1,redo  =False,integrate_from_go  =False,normalise_across_clusters=False):
    params = deepcopy(original_params)

    params['threshold_per_condition'] = threshold_per_condition
    params['tlim']  = tlim
    params['tau'] = tau
    params['threshold_resolution'] = threshold_resolution
    params['score_reps'] = score_reps
    params['integrate_from_go'] =integrate_from_go
    params['normalise_across_clusters'] = normalise_across_clusters
    params['redo'] = redo
    return load_data('../data/', 'reaction_time_analyses', params['sim_params'], old_key_code=False, ignore_keys=[''])



def _get_mo_times(params):
    monkey=params['monkey']
    condition = params['condition']

    toc = joe_and_lili.get_toc(extra_filters = [['monkey','=',monkey]])
    gns = pylab.unique(toc['global_neuron'])

    rts = []
    for gn in gns:
        data = analyses.load_data(gn,condition)
        new_rts = data['eventtimes'][:,data['event_names'] == 'MO']
        # get rid of strange nan to int conversions
        new_rts = new_rts[new_rts<10000]
        new_rts = new_rts[new_rts>-10000]
        rts +=new_rts.tolist()
    
    return pylab.array(rts).flatten()

    


def reaction_time_plot(monkey,nbins = 40,condition_colors = ['0','0.3','0.6']):
    
    rts = []
    minrt = 1000000
    maxrt = 0
    for condition in [1,2,3]:
        params = {'monkey':monkey,'condition':condition}
        rts.append(organiser.check_and_execute(params, _get_mo_times, 'reaction_times',redo  =False) )
        minrt = min(minrt,min(rts[-1]))
        maxrt = max(maxrt,max(rts[-1]))


    bins = pylab.linspace(minrt,maxrt,nbins)
    print(type(rts))
    for condition in [1,2,3]:
        plotbins = (bins[1:]+bins[:-1])/2.
        print('mean RT experiment: ', pylab.median(pylab.array(rts[condition-1])))
        pylab.hist(pylab.array(rts[condition-1]),bins,histtype = 'step',label = 'condition '+str(condition),color = condition_colors[condition-1],lw = 1.,normed = True)
    
    ##############
    ##test#######
    import scipy.stats as ss
    min_len = min(len(rts[1]),len(rts[2]))
    print('sample size monkey', min_len)
    print('wilcoxon test monkey', ss.wilcoxon(rts[1][:min_len],rts[2][:min_len]))
    pylab.xlim(1400,2000)
        





    

if __name__ == '__main__':
    sim_params = {'randseed':8721,'trials':150,'N_E':1200,'N_I':300,'I_th_E':1.25,'I_th_I':0.78,'Q':6,'rs_stim_amp':0,'n_jobs':12,'conditions':[1,2,3]}

    settings = [{'randseed':7745,'jep':3.3,'jipratio':0.75,'condition_stim_amps':[0.15,0.15,0.15],'rs_stim_amp':0.15,'rs_length':400},
                {'randseed':5362,'jep':2.8,'jipratio':0.75,'condition_stim_amps':[0.15,0.15,0.15],'rs_stim_amp':0.15,'rs_length':400}]

    settings = [{'randseed':7745,'jep':3.3,'jipratio':0.75,'condition_stim_amps':[0.15,0.15,0.15],'rs_stim_amp':0.15,'rs_length':400}]

    settings = [{'randseed':7745,'jep':3.3,'jipratio':0.75,'condition_stim_amps':[0.15,0.15,0.15],'rs_stim_amp':0.15,'rs_length':400,'trials':2000}]

    x_label_val=-0.5                            
    fig = plotting.nice_figure(ratio = 1.)
    nrows = 2
    ncols = 2
    gs = pylab.GridSpec(nrows,ncols,top=0.9,bottom=0.1,hspace = 0.4,wspace = 0.9,left = 0.2,right = 0.88,height_ratios = [2,1])
    subplotspec = gs.new_subplotspec((1,1), colspan=1,rowspan=1)
    ax2 = plotting.ax_label1(plotting.simpleaxis(pylab.subplot(subplotspec)),'c',x=x_label_val)
    ax2.set_title('Behaving monkey')
    labelsize=5
    cond_colors = ['navy','royalblue','lightskyblue']
    reaction_time_plot('joe', condition_colors = cond_colors)
    pylab.xlabel('reaction time [ms]')
    pylab.ylabel('P')
    pylab.axvline(1500,linestyle = '-',color = 'k',lw = 0.5)
    pylab.ylim(0,0.015)    
    pylab.yticks([0,0.004,0.008,0.012])
    pylab.legend(frameon = False,fontsize = 6,loc = 'upper right', bbox_to_anchor=(1.45, 1.1))
    pylab.xticks([1500,1600,1700,1800,1900,2000])
    ax2.set_xticklabels(['RS', '100','200','300','400','500'])
    condition_alpha = 1.
                
    condition_colors = [[0,0,0,condition_alpha],[0.4,0.4,0.4,condition_alpha],[0.6,0.6,0.6,condition_alpha]]
    tlim = [-500,2000]

    for setno,setting in enumerate(settings[:1]):
        for k in list(setting.keys()):
            sim_params[k] = setting[k]

        for tau in [50.]:
            for threshold_per_condition in [False]:
                for integrate_from_go in [False]:
                    for min_count_rate in [7.5]:
                        for align_ts in [False]:

                            params = {'sim_params':sim_params}
                            result = get_reaction_time_analysis(params,tlim  =tlim,redo = False,tau  =tau,integrate_from_go = integrate_from_go,normalise_across_clusters=True,threshold_per_condition = threshold_per_condition)
                            print(result['integrals'].shape)
                            print(list(result.keys()))
                            
                            rts = result['rts']
                            conditions = result['conditions']
                            directions = result['directions']
                            predictions = result['predictions']
                            print(predictions)
                            print(directions)
                            correct= directions == predictions
                            correct_inds = find(correct)
                            incorrect_inds = find(correct==False)
                            subplotspec = gs.new_subplotspec((0,0), colspan=2,rowspan=1)
                            ax1 = plotting.ax_label1(plotting.simpleaxis(pylab.subplot(subplotspec)),'a',x=x_label_val/3)
                            pylab.suptitle('Example trial of motor cortical attractor model')
                            
                            print('find correct cond==3', find(correct*(conditions==3)))
                            plot_trial = find(correct*(conditions==3))[8]#[6]
                            print('plot trial',plot_trial)
                            pylab.xticks([-500,0,1000])
                            pylab.gca().set_xticklabels(['0', '500','1500'])

                            print('direction prediction condition',
                                  directions[plot_trial],
                                  predictions[plot_trial])

                            data  = get_simulated_data(params['sim_params'],datafile = 'simulated_data_fig6')
                            print('got the data!!!')
                            cut_window = [-500,2000]
                            trial_starts = data['trial_starts']
                            spiketimes = spiketools.cut_spiketimes(data['spiketimes'],tlim = pylab.array(cut_window)+trial_starts[plot_trial])
                            spiketimes[0] -= trial_starts[plot_trial]
                            pylab.plot(spiketimes[0],spiketimes[1],'.',ms =0.5,color = '0.5')
                            pylab.xlim(cut_window)
                            Q = params['sim_params']['Q']
                            N_E = params['sim_params']['N_E']
                            cluster_size = N_E/Q
                            direction_clusters =  data['direction_clusters']
                            integrals = result['integrals']
                            time = result['time']
                            threshold = result['condition_thresholds'][conditions[plot_trial]]
                            pylab.axvline(1000,linestyle = '--',color ='k',lw = 0.5)
                            direction_clusters = pylab.array(direction_clusters).flatten()
                            print(direction_clusters)
                            for cluster in range(6):

                                pylab.text(2000,(cluster+0.5)*cluster_size,r'\textbf{'+str(cluster+1)+'}',va = 'center',ha = 'left')
                                direction = find(direction_clusters == cluster)[0]
                                
                                
                                pylab.plot(time,cluster*cluster_size +integrals[direction,plot_trial]*cluster_size*0.8,color = 'k')
                                print(integrals[direction,plot_trial])
                                pylab.plot([1000,2000],[cluster*cluster_size +threshold*cluster_size*0.8]*2,'--k',lw =0.5)
                                
                                if (direction+1) == directions[plot_trial]:
                                    try:
                                        crossing = find((integrals[direction,plot_trial]>threshold)*(time>1000))[0]
                                        print(crossing)
                                        pylab.plot(time[crossing],cluster*cluster_size +threshold*cluster_size*0.8,'ok',ms = 4)
                                    except:
                                        print('no crossing')
                                    
                            pylab.xlim(time.min(),time.max())
                            pylab.ylim(0,N_E)
                            pylab.ylabel('unit')
                            pylab.xlabel('time [ms]')
                            pylab.text(-50,1250,'PS')
                            pylab.text(950,1250,'RS')
                            subplotspec = gs.new_subplotspec((1,0), colspan=1,rowspan=1)
                            ax2 = plotting.ax_label1(plotting.simpleaxis(pylab.subplot(subplotspec)),'b',x=x_label_val)
                            ax2.set_title('Attractor model')
                            
              
                            
                            
                            for condition in [1,2,3]:
                                
                                rt = rts[(conditions == condition)*correct]
                                bins = pylab.linspace(0,500,15)
                                print('cond len_rt',condition,len(rt))
                                print('mediann', pylab.median(rt))
                                pylab.hist(rt,bins,histtype = 'step',facecolor = cond_colors[condition-1],normed = True,edgecolor  = cond_colors[condition-1],label = 'condtion '+str(condition))
                                pylab.xlim(1400,2000)
                            import scipy.stats as ss
                            min_len = min(len(rts[(conditions == 2)*correct]),len(rts[(conditions == 3)*correct]))
                            print('sample size model:', min_len)
                            print('wilcoxon test', ss.wilcoxon(rts[(conditions == 2)*correct][:min_len],rts[(conditions == 3)*correct][:min_len]))
                            print('condition 1', rts[(conditions == 1)*correct])

                                
                            pylab.xlim(-100,500)
                            pylab.xticks([0,100,200,300,400,500])
                            pylab.gca().set_xticklabels(['RS', '100','200','300','400','500'])
                            pylab.ylim(0,0.015)
                            pylab.yticks([0,0.004,0.008,0.012])                            
                            pylab.ylabel('P')
                            pylab.xlabel('reaction time [ms]')
                            pylab.axvline(0,linestyle = '-',color = 'k',lw = 0.5)             
                            
                            
                



    pylab.savefig('fig6.pdf')
    pylab.show()



