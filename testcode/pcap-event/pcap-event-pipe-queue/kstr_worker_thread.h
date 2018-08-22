#ifndef __WORKER_THREAD_
#define __WORKER_THREAD_
#include "pub_head.h"
#include "kstr_mq_queue.h"

typedef struct {
	int idx ;
	pthread_t thread_id;
	struct event_base *base;   //every thread own event base
	struct event notify_event; //notify event	
	int notify_receive_fd;     // pipe recv
	int notify_send_fd; 	   //pipe send 
	queue_t* msgq;             //msg  queue 
} event_thread_ctx_t;

event_thread_ctx_t * worker_thread_init(int nthreads) ;

void worker_thread_close( event_thread_ctx_t* ctx, int threads );

#endif