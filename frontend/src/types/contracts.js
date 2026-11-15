/** @typedef {{id:number,code:string,team:string,before:number|null,after:number|null,note:string}} Pair */
/** @typedef {{id:number,name:string,team:string,state:'queued'|'running'|'done'|'failed',result:null|{snapshot:Array,settings?:{iterations:number,batch_size:number},progress?:object,completed?:number,[k:string]:any},error:string}} Evaluation */
/** @typedef {{id:number,evaluation_id:number,decision:string,note:string,status:string}} Adoption */
