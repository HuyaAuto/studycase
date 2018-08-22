#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <pthread.h>

#include <sys/types.h>
#include <sys/socket.h>

#include <event.h>

#include <arpa/inet.h>

#include <memory.h>

const int thread_num = 10;
#define BUF_SIZE 1024


typedef struct {
    pthread_t tid;
    pid_t     pid;
    struct event_base *base;
    struct event event;
    int read_fd;
    int write_fd;
    //queue<int> q;
    int f_connect;
    char * buffer;
}LIBEVENT_THREAD;                 //需要保存的信息结构，用于管道通信和基事件的管理

typedef struct {
    pthread_t tid;
    struct event_base *base;
}DISPATCHER_THREAD;

LIBEVENT_THREAD *threads ;

void on_read(int sock, short event, void* arg)
{
    printf("on_read() called, sock=%d\n", sock);
    if(NULL == arg){
        return;
    }
    LIBEVENT_THREAD* event_thread = (LIBEVENT_THREAD*) arg;//获取传进来的参数
    char* buffer = (char *)malloc(BUF_SIZE);
    memset(buffer, 0, sizeof(char)*BUF_SIZE);
    //--本来应该用while一直循环，但由于用了libevent，只在可以读的时候才触发on_read(),故不必用while了
    int size = read(sock, buffer, BUF_SIZE);
    if(0 == size){//说明socket关闭
        printf("read size is 0 for socket:%d\n", sock);
        //  destroy_sock_ev(event_struct);

        //event_thread->q.pop();
        close(sock);
        return;
    }
    printf("i have receive: %s\n", buffer);

    free(buffer);
    printf("on_read() finished, sock=%d\n",sock);

}

static void thread_libevent_process(int fd, short which, void *arg)
{
    int ret;
    char buf[128];
    LIBEVENT_THREAD *me = (LIBEVENT_THREAD *) arg;

    int fdconnect;

    if (fd != me->read_fd) {
        printf("thread_libevent_process error : fd != me->read_fd\n");
        exit(1);
    }

    ret = read(fd, buf, 128);
    if (ret > 0) 
    {

        buf[ret] = '\0';

        printf("thread %llu receive message : %s\n", (unsigned long long)me->tid, buf);
        printf("thread pid:%lu\n", (unsigned long long)me->pid);

    }

    printf("thread_libevent_process\n");

    /*if(me->q.size()>0)
      {
      fdconnect=me->q.front();
      me->q.pop();

      ret = read(fd, buf, 128);
      if (ret > 0) 
      {

      buf[ret] = '\0';

      printf("thread %llu receive message : %s\n", (unsigned long long)me->tid, buf);

      }
      }*/

    /*if(me->q.size()>0)
      {
      fdconnect=me->q.front();

      cout<<"thread_libevent_process succeed "<<endl;
    //me->q.pop();
    }

    else
    return ;*/

    fdconnect=me->f_connect;

    struct event* read_ev = (struct event*)malloc(sizeof(struct event));//发生读事件后，从socket中取出数据

    event_set(read_ev, fdconnect, EV_READ|EV_PERSIST, on_read, me);

    event_base_set(me->base, read_ev);

    event_add(read_ev, NULL);

    return;
}

void thread_init()
{
    int ret;
    int fd[2];
    int i;
    for (i = 0; i < thread_num; i++) {

        ret = socketpair(AF_LOCAL, SOCK_STREAM, 0, fd);

        if (ret == -1) {
            perror("socketpair()");
            return  ;
        }

        threads[i].read_fd  = fd[0];
        threads[i].write_fd = fd[1];

        threads[i].base = event_init();

        if (threads[i].base == NULL) {
            perror("event_init()");
            return ;
        }

        event_set(&threads[i].event,threads[i].read_fd, EV_READ | EV_PERSIST, thread_libevent_process, &threads[i]);

        event_base_set(threads[i].base, &threads[i].event);
        if (event_add(&threads[i].event, 0) == -1) {
            perror("event_add()");
            return  ;
        }

        printf("thread_init succeed\n");

    }
}

void * worker_thread(void *arg)
{
    LIBEVENT_THREAD *me = (LIBEVENT_THREAD *)arg;
    me->tid = pthread_self();

    //event_base_loop(me->base, 0);

    event_base_dispatch(me->base);//每个工作线程都在检测event链表是否有事件发生

    return NULL;
}

void CreatPhreadPool()
{
    int i;
    for (i = 0; i < thread_num; i++) {
        pthread_create(&threads[i].tid, NULL, worker_thread, &threads[i]);
        threads[i].pid = getpid() + i +1;
    }

    printf("CreatPhreadPool\n");
}

int getSocket(){
    int fd =socket( AF_INET, SOCK_STREAM, 0 );
    if(-1 == fd){
        printf("Error, fd is -1\n");
    }
    return fd;
}

int last_thread=0;

void event_handler(int sock, short event, void* arg)  //添加其他信息
{
    struct sockaddr_in remote_addr;
    int sin_size=sizeof(struct sockaddr_in);
    int new_fd = accept(sock,  (struct sockaddr*) &remote_addr, (socklen_t*)&sin_size);    //如果线程池已用完，怎么办呢？
    if(new_fd < 0){
        printf("Accept error in on_accept()\n");
        return;
    }
    printf("new_fd accepted is:%d\n", new_fd);

    int tid = (last_thread + 1) % thread_num;        //memcached中线程负载均衡算法

    LIBEVENT_THREAD *thread = threads + tid;

    last_thread = tid;  

    thread->f_connect=new_fd;

    write(thread->write_fd, "have packet", 11);

    printf("on_accept() finished for fd=%d\n", new_fd);
}

DISPATCHER_THREAD dispatcher_thread;        //用于设置主线程的结构变量

int main(int argc, char** argv)  
{
    threads = (LIBEVENT_THREAD *) calloc(thread_num, sizeof(LIBEVENT_THREAD));
    thread_init();

    CreatPhreadPool();

    int fd_listen = getSocket();
    if(fd_listen <0){
        printf("Error in main(), fd<0\n");
    }
    //cout<<"main() fd="<<fd<<endl;
    //----为服务器主线程绑定ip和port------------------------------
    struct sockaddr_in local_addr; //服务器端网络地址结构体
    memset(&local_addr,0,sizeof(local_addr)); //数据初始化--清零
    local_addr.sin_family=AF_INET; //设置为IP通信
    local_addr.sin_addr.s_addr=inet_addr(argv[1]);//服务器IP地址
    local_addr.sin_port=htons(atoi(argv[2])); //服务器端口号
    int bind_result = bind(fd_listen, (struct sockaddr*) &local_addr, sizeof(struct sockaddr));
    if(bind_result < 0){
        printf("Bind Error in main()\n");
        return -1;
    }
    printf("bind_result=%d\n", bind_result);
    listen(fd_listen, 10);

    evutil_make_socket_nonblocking(fd_listen);
    //-----设置libevent事件，每当socket出现可读事件，就调用on_accept()------------
    struct event_base* base = event_base_new();
    dispatcher_thread.base=base;
    dispatcher_thread.tid = pthread_self();

    struct event listen_ev;
    event_set(&listen_ev, fd_listen, EV_READ|EV_PERSIST, event_handler, NULL);
    event_base_set(dispatcher_thread.base, &listen_ev);
    event_add(&listen_ev, NULL);
    event_base_dispatch(dispatcher_thread.base);//监听线程
    //------以下语句理论上是不会走到的---------------------------
    printf("event_base_dispatch() in main() finished\n");
    //----销毁资源-------------
    event_del(&listen_ev);
    event_base_free(dispatcher_thread.base);
    printf("main() finished\n");
    while(1)
    {
        sleep(100);
    }
    return 0;

}
